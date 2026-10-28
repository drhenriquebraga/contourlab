# -*- coding: utf-8 -*-
import io
import os
import re
import shutil
import sys
import tempfile
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.abspath(os.path.join(AQUI, ".."))
APP = os.path.join(RAIZ, "app")
sys.path.insert(0, APP)

import radai_batch as L
import radai_triage as T


def lote_py_txt():
    return io.open(_componentes.fonte("app/radai_batch.py"),
                   encoding="utf-8").read()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _cleanup
_cleanup.adotar_prefixo('radai_ac_lote')
_cleanup.adotar_prefixo('radai_lote_rs_')
_cleanup.adotar_prefixo('radai_t_')
_cleanup.adotar_prefixo('radai_portal_')
_cleanup.adotar_prefixo('radai_zipabs_')
_cleanup.adotar_prefixo('radai_tx_')

import tempfile as _tempfile
import _componentes
os.environ["RADAI_CALIB_DIR"] = _tempfile.mkdtemp(prefix="radai_ac_lote_")

os.environ["RADAI_REGISTRO_DIR"] = _tempfile.mkdtemp(prefix="radai_ac_lote_reg_")
_REGISTRO_DO_REPOSITORIO = _componentes.fonte("app/registro")


def _casos_do_repositorio():
    d = os.path.join(_REGISTRO_DO_REPOSITORIO, "casos")
    try:
        nomes = set(os.listdir(d))
    except OSError:
        nomes = set()
    try:
        with io.open(os.path.join(_REGISTRO_DO_REPOSITORIO, "indice.jsonl"),
                     encoding="utf-8", errors="replace") as f:
            linhas = sum(1 for _ in f)
    except (IOError, OSError):
        linhas = 0
    return nomes, linhas


_CASOS_ANTES = _casos_do_repositorio()



OK = 0
FALHAS = 0
VERBOSO = "-v" in sys.argv


def checar(nome, ok, detalhe=""):
    global OK, FALHAS
    if ok:
        OK += 1
    else:
        FALHAS += 1
    if VERBOSO or not ok:
        print("  %-6s %s%s" % ("OK" if ok else "FALHA", nome,
                               ("  [%s]" % detalhe) if detalhe else ""))


def secao(t):
    if VERBOSO:
        print("\n-- %s %s" % (t, "-" * max(0, 58 - len(t))))


EXAME = [(1, 2, 2.00, "FL02", "SCOUT"),
         (3, 80, 1.00, "FC07", "TORAX 1MM"),
         (4, 30, 8.00, "FC07", "TORAX 8MM"),
         (5, 80, 1.00, "FC51", "TORAX PULMAO"),
         (7, 40, 3.00, "FC51", "TORAX 3MM")]


def _serie(destino, numero, cortes, espessura, kernel, desc,
           modalidade="CT"):
    import numpy as np
    from pydicom.dataset import Dataset, FileDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid

    serie_uid = generate_uid()
    estudo_uid = generate_uid()
    os.makedirs(destino, exist_ok=True)
    for i in range(cortes):
        px = np.fromfunction(
            lambda y, x: ((x * 37 + y * 91 + i * 53) % 900) - 450,
            (8, 8)).astype(np.int16).tobytes()
        meta = Dataset()
        meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
        meta.MediaStorageSOPInstanceUID = generate_uid()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        meta.ImplementationClassUID = generate_uid()
        ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)
        ds.SOPClassUID = meta.MediaStorageSOPClassUID
        ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
        ds.Modality = modalidade
        ds.PatientName = "FANTOMA^TESTE"
        ds.PatientID = "FANTOMA001"
        ds.StudyInstanceUID = estudo_uid
        ds.SeriesInstanceUID = serie_uid
        ds.FrameOfReferenceUID = estudo_uid
        ds.SeriesNumber = numero
        ds.InstanceNumber = i + 1
        ds.SeriesDescription = desc
        ds.StudyDate = ds.SeriesDate = "20260101"
        ds.SliceThickness = espessura
        ds.ConvolutionKernel = kernel
        ds.ImagePositionPatient = [0.0, 0.0, i * espessura]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing = [0.7, 0.7]
        ds.Rows = ds.Columns = 8
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.BitsAllocated = ds.BitsStored = 16
        ds.HighBit = 15
        ds.PixelRepresentation = 1
        ds.RescaleIntercept = 0
        ds.RescaleSlope = 1
        ds.PixelData = px
        alvo = os.path.join(destino, "IM%05d" % (i + 1))
        try:
            ds.save_as(alvo, enforce_file_format=True)
        except TypeError:
            ds.save_as(alvo, write_like_original=False)
    return serie_uid


def montar_zip(base):
    cru = os.path.join(base, "cru")
    for (n, cortes, esp, k, desc) in EXAME:
        _serie(os.path.join(cru, "exam", "S%d" % n), n, cortes, esp, k, desc)

    ruido = os.path.join(cru, "csc")
    os.makedirs(ruido, exist_ok=True)
    for i in range(20):
        open(os.path.join(ruido, "prev%03d.jpg" % i), "wb").write(b"\xff\xd8\xff" * 40)
    for nome in ("viewer.dll", "codec.ocx", "licenca.lic", "LEIA.txt", "menu.html"):
        open(os.path.join(ruido, nome), "wb").write(b"MZ" + b"\0" * 500)

    z = os.path.join(base, "EXAME_PORTAL.zip")
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as f:
        for raiz, _, arqs in os.walk(cru):
            for a in arqs:
                fp = os.path.join(raiz, a)
                f.write(fp, os.path.relpath(fp, cru))
    return z


def teste_zip_extrai_o_que_e_imagem():
    secao("zip: extrai DICOM sem extensão, descarta o visualizador")
    base = tempfile.mkdtemp(prefix="radai_t_")
    try:
        z = montar_zip(base)
        with zipfile.ZipFile(z) as f:
            no_zip = len([i for i in f.infolist() if not i.is_dir()])
        pasta, erro = L.preparar_zip(z, os.path.join(base, "out"))
        checar("extraiu sem erro", not erro, erro)
        checar("devolveu pasta", bool(pasta) and os.path.isdir(pasta))

        saiu = []
        for raiz, _, arqs in os.walk(pasta):
            saiu += [os.path.join(raiz, a) for a in arqs]
        cortes = sum(c for (_, c, _, _, _) in EXAME)
        checar("trouxe todo o DICOM (sem extensão, inclusive)",
               len(saiu) == cortes, "%d de %d, zip tinha %d" % (len(saiu), cortes, no_zip))
        checar("e deixou prévia, DLL, OCX e licença de fora",
               not [a for a in saiu if os.path.splitext(a)[1].lower()
                    in (".jpg", ".dll", ".ocx", ".lic", ".txt", ".html")])
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_zip_nao_funde_as_series():
    secao("zip: as séries não se fundem")
    base = tempfile.mkdtemp(prefix="radai_t_")
    try:
        z = montar_zip(base)
        pasta, erro = L.preparar_zip(z, os.path.join(base, "out"))
        checar("preparou", not erro, erro)
        series = L.varrer(pasta, min_cortes=1)
        checar("achou as %d séries, separadas" % len(EXAME),
               len(series) == len(EXAME), str(len(series)))
        uids = set(s["uid"] for s in series)
        checar("com UID distinto cada uma", len(uids) == len(EXAME), str(len(uids)))

        por_num = dict((int(s["numero"]), s) for s in series if s["numero"])
        for (n, cortes, esp, k, _d) in EXAME:
            checar("série %d com %d cortes" % (n, cortes),
                   por_num.get(n, {}).get("cortes") == cortes,
                   str(por_num.get(n, {}).get("cortes")))
            checar("série %d com espessura %.2f" % (n, esp),
                   abs((por_num.get(n, {}).get("espessura_mm") or -1) - esp) < 1e-6,
                   str(por_num.get(n, {}).get("espessura_mm")))
            checar("série %d com kernel %s" % (n, k),
                   por_num.get(n, {}).get("kernel") == k,
                   str(por_num.get(n, {}).get("kernel")))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_apontar_a_pasta_acha_o_exame_empacotado():
    secao("pasta: o exame dentro do .zip também é achado")
    base = tempfile.mkdtemp(prefix="radai_t_")
    try:
        montar_zip(base)
        pasta = os.path.join(base, "guardados")
        os.makedirs(pasta)
        shutil.move(os.path.join(base, "EXAME_PORTAL.zip"),
                    os.path.join(pasta, "EXAME_PORTAL.zip"))

        sem = L.varrer(pasta, min_cortes=1)
        checar("sem incluir_zips não acha nada (era o defeito)", not sem, str(len(sem)))
        com = L.varrer(pasta, min_cortes=1, incluir_zips=True)
        checar("apontando a pasta, acha as %d séries" % len(EXAME),
               len(com) == len(EXAME), str(len(com)))
        checar("e todas sabem de que .zip vieram",
               all(s.get("zip") for s in com))
        checar("nenhuma finge ter RTSTRUCT ao lado",
               not any(s.get("tem_rs") for s in com))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_espiar_nao_escreve_nada():
    secao("pasta: espiar o .zip não extrai")
    base = tempfile.mkdtemp(prefix="radai_t_")
    try:
        z = montar_zip(base)
        antes = dict(L._EXTRAIDOS)
        series, erro = L.espiar_zip(z)
        checar("espiou sem erro", not erro, erro)
        checar("achou as %d séries" % len(EXAME), len(series) == len(EXAME),
               str(len(series)))
        checar("e não extraiu nada", L._EXTRAIDOS == antes)
        checar("cada série sabe onde está DENTRO do pacote",
               all("/" in (s["pasta"] or "") or s["pasta"] == "" for s in series),
               str([s["pasta"] for s in series][:2]))

        alvo = max(series, key=lambda x: x["cortes"])
        pasta, erro = L.resolver_pasta(alvo)
        checar("resolver_pasta extrai e acha a subpasta", bool(pasta) and not erro, erro)
        checar("com os cortes daquela série lá dentro",
               pasta and len(os.listdir(pasta)) == alvo["cortes"],
               "%d vs %d" % (len(os.listdir(pasta)) if pasta else -1, alvo["cortes"]))
        shutil.rmtree(pasta, ignore_errors=True)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_zip_ilegivel_nao_derruba_a_pasta():
    secao("pasta: .zip ilegível não derruba os outros")
    base = tempfile.mkdtemp(prefix="radai_t_")
    try:
        pasta = os.path.join(base, "guardados")
        os.makedirs(pasta)
        montar_zip(base)
        shutil.move(os.path.join(base, "EXAME_PORTAL.zip"),
                    os.path.join(pasta, "bom.zip"))
        open(os.path.join(pasta, "quebrado.zip"), "wb").write(b"nao sou um zip")
        com = L.varrer(pasta, min_cortes=1, incluir_zips=True)
        checar("o exame bom continua aparecendo", len(com) == len(EXAME), str(len(com)))
        s, erro = L.espiar_zip(os.path.join(pasta, "quebrado.zip"))
        checar("e o quebrado explica por quê", bool(erro) and not s, erro)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_zip_diz_o_motivo_em_portugues():
    secao("zip: erro explicado, nunca exceção na cara do médico")
    base = tempfile.mkdtemp(prefix="radai_t_")
    try:
        pasta, erro = L.preparar_zip(os.path.join(base, "nao_existe.zip"))
        checar("arquivo ausente: recusa", not pasta)
        checar("e diz que não achou", u"achei" in erro, erro)

        falso = os.path.join(base, "falso.zip")
        open(falso, "wb").write(b"isto nao e um zip")
        pasta, erro = L.preparar_zip(falso, os.path.join(base, "o1"))
        checar("zip inválido: recusa", not pasta)
        checar("e diz que não é .zip", u"zip" in erro.lower(), erro)

        vazio = os.path.join(base, "so_ruido.zip")
        with zipfile.ZipFile(vazio, "w") as f:
            f.writestr("a/previa.jpg", b"\xff\xd8\xff")
            f.writestr("a/viewer.dll", b"MZ")
        pasta, erro = L.preparar_zip(vazio, os.path.join(base, "o2"))
        checar("zip sem imagem: recusa", not pasta)
        checar("e diz que não há imagem", u"imagem" in erro.lower(), erro)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_zip_extrai_uma_vez_so():
    secao("zip: extrai uma vez por arquivo")
    base = tempfile.mkdtemp(prefix="radai_t_")
    try:
        z = montar_zip(base)
        p1, e1 = L.preparar_zip(z)
        p2, e2 = L.preparar_zip(z)
        checar("as duas chamadas dão certo", not e1 and not e2, e1 or e2)
        checar("e devolvem a MESMA pasta", p1 == p2, "%s vs %s" % (p1, p2))

        with zipfile.ZipFile(z, "a") as f:
            f.writestr("extra/nota", b"\0" * 8)
        p3, e3 = L.preparar_zip(z)
        checar("zip alterado extrai de novo", p3 != p1, "%s" % p3)
        for p in (p1, p3):
            shutil.rmtree(p, ignore_errors=True)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_extracao_sobrevive_ao_reinicio():
    secao("zip: a extração é a mesma depois de reiniciar")
    base = tempfile.mkdtemp(prefix="radai_t_")
    try:
        z = montar_zip(base)
        p1, e1 = L.preparar_zip(z)
        checar("extraiu", bool(p1) and not e1, e1)

        L._EXTRAIDOS.clear()
        p2, e2 = L.preparar_zip(z)
        checar("depois de perder o cache, acha a MESMA pasta", p1 == p2,
               "%s vs %s" % (p1, p2))

        marca = os.path.join(p1, "RS_RadAI_FANTOMA.dcm")
        open(marca, "wb").write(b"\0" * 8)
        L._EXTRAIDOS.clear()
        p3, _ = L.preparar_zip(z)
        checar("e o RTSTRUCT gravado sobrevive",
               os.path.isfile(os.path.join(p3, "RS_RadAI_FANTOMA.dcm")))

        z2 = os.path.join(base, "OUTRO.zip")
        shutil.copy2(z, z2)
        open(z2, "ab").write(b"\0")
        p4, _ = L.preparar_zip(z2)
        checar("exame diferente vai para pasta diferente", p4 != p1)
        for p in (p1, p4):
            shutil.rmtree(p, ignore_errors=True)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_nao_extrai_exame_para_dentro_do_programa():
    secao("zip: não extrai para dentro da árvore do programa")
    base = tempfile.mkdtemp(prefix="radai_t_")
    try:
        z = montar_zip(base)
        pasta, erro = L.preparar_zip(z, os.path.join(RAIZ, "_exame_teste"))
        checar("recusa extrair para dentro do projeto", not pasta)
        checar("e diz por que", u"programa" in erro.lower(), erro)
        checar("e não criou a pasta",
               not os.path.isdir(os.path.join(RAIZ, "_exame_teste")))

        os.environ["RADAI_ARVORE_SINCRONIZADA"] = base
        try:
            pasta, erro = L.preparar_zip(z, os.path.join(base, "dentro"))
            checar("recusa árvore sincronizada declarada", not pasta)
            checar("e diz que é a nuvem", u"nuvem" in erro.lower(), erro)
        finally:
            del os.environ["RADAI_ARVORE_SINCRONIZADA"]

        pasta, erro = L.preparar_zip(z, os.path.join(base, "ok"))
        checar("pasta de trabalho normal é aceita", bool(pasta) and not erro, erro)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_zip_com_caminho_para_fora_e_ignorado():
    secao("zip: nome que sobe de pasta é descartado")
    base = tempfile.mkdtemp(prefix="radai_t_")
    try:
        z = os.path.join(base, "mau.zip")
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("../../fugiu", b"\0" * 8)
            f.writestr("exam/IM00001", b"\0" * 8)
        alvo = os.path.join(base, "out")
        pasta, erro = L.preparar_zip(z, alvo)
        checar("extraiu o que era legítimo", bool(pasta), erro)
        fugiu = os.path.join(os.path.dirname(os.path.dirname(alvo)), "fugiu")
        checar("e nada escapou do destino", not os.path.exists(fugiu), fugiu)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_a_serie_sugerida_e_a_que_serve():
    secao("escolha: do .zip à série sugerida")
    base = tempfile.mkdtemp(prefix="radai_t_")
    try:
        z = montar_zip(base)
        pasta, erro = L.preparar_zip(z, os.path.join(base, "out"))
        checar("preparou", not erro, erro)
        ord_ = T.classificar_series(L.varrer(pasta, min_cortes=1))

        sug = [s for s in ord_ if s["sugerida"]]
        checar("sugere exatamente uma", len(sug) == 1, str(len(sug)))
        checar("e é a de 1 mm com kernel de partes moles (série 3)",
               sug and int(sug[0]["numero"]) == 3,
               str(sug[0].get("numero")) if sug else "-")
        checar("nenhuma série some da lista", len(ord_) == len(EXAME), str(len(ord_)))

        por_num = dict((int(s["numero"]), s) for s in ord_ if s["numero"])
        checar("a de 8 mm é recusada", not por_num[4]["torax"]["serve"])
        checar("dizendo que é a espessura",
               "8.00 mm" in " ".join(por_num[4]["torax"]["impedimentos"]),
               str(por_num[4]["torax"]["impedimentos"]))
        checar("o localizador de 2 cortes é recusado", not por_num[1]["torax"]["serve"])
        checar("e toda recusada explica por quê",
               all(s["torax"]["impedimentos"] for s in ord_ if not s["torax"]["serve"]))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_numero_do_dicom_nao_explode():
    secao("varredura: número do DICOM ausente ou estranho")
    checar("vazio vira None", L._num("") is None)
    checar("None vira None", L._num(None) is None)
    checar("texto vira None", L._num("N/A") is None)
    checar("número vira float", L._num("1.25") == 1.25)
    try:
        from pydicom.valuerep import DSfloat
        checar("DSfloat vira float", L._num(DSfloat("3.0")) == 3.0)
    except Exception as e:
        checar("DSfloat vira float", False, str(e))
    checar("série sem espessura ainda é avaliada",
           T.avaliar_serie({"cortes": 100, "espessura_mm": None})["serve"] is False)


def teste_uma_serie_nao_processa_sem_coordenacao():
    secao("processar uma: sem marcadores, recusa")
    guardado = dict(L._CFG)
    try:
        L._CFG.clear()
        r = L.iniciar_uma({"uid": "1.2.3", "pasta": "C:\\nada"})
        checar("recusa sem o lote montado", not r.get("ok"))
        checar("e diz que falta a coordenação",
               "coordenacao" in (r.get("erro") or "").lower(), r.get("erro", ""))

        L._CFG.update({"tasks": ["total"], "device": "cpu"})
        r = L.iniciar_uma({"uid": "1.2.3", "pasta": "C:\\nada"})
        checar("com config mas sem marcadores, também recusa", not r.get("ok"))
        checar("citando o lock", "lock" in (r.get("erro") or "").lower(),
               r.get("erro", ""))
    finally:
        L._CFG.clear()
        L._CFG.update(guardado)


def teste_uma_serie_usa_a_config_do_lote():
    secao("processar uma: a configuração é a do lote")
    fonte = io.open(_componentes.fonte("app/radai_batch.py"), encoding="utf-8").read()
    corpo = fonte.split("def iniciar_uma(")[1].split("\ndef ")[0]
    for chave in ("device", "marcadores", "maquina",
                  "suavizar_mm", "timeout_task_s"):
        checar("%s vem do _CFG" % chave, '_CFG.get("%s"' % chave in corpo)
    checar("tasks e so a do chamador: a lista do config nao e mais o recuo",
           "tasks=tasks," in corpo and '_CFG.get("tasks")' not in corpo)
    checar("  e o teto do NV e o de qualquer task (TIMEOUT_NV_H saiu)",
           '_CFG.get("timeout_vista_s"' not in corpo)

    codigo = corpo
    for tres in ('"""', "'''"):
        codigo = "".join(codigo.split(tres)[::2])
    checar("não há lista de tasks escrita no código",
           "total" not in codigo and "lung_vessels" not in codigo, codigo[:90])


def teste_o_tx_sai_pelos_dois_caminhos():
    secao("_tx: uma funcao so, chamada pelos dois caminhos")
    motor_py = io.open(_componentes.fonte("app/engine.py"), encoding="utf-8").read()
    lote_py = io.open(_componentes.fonte("app/radai_batch.py"), encoding="utf-8").read()
    vigia_py = io.open(_componentes.fonte("app/radai_watcher.py"), encoding="utf-8").read()

    checar("o nome antigo da gravacao nao voltou",
           "def entregar_torax(" not in motor_py,
           "isto mede o NOME. Quem prova que nada grava e a checagem que "
           "lista a pasta depois de rodar o lote")
    checar("nem os chamadores dele",
           "engine.entregar_torax(" not in lote_py
           and "engine.entregar_torax(" not in vigia_py)
    checar("e nenhum dos dois ganhou copia da montagem",
           "class _Torax" not in lote_py and "class _Torax" not in vigia_py)
    checar("nem segunda lista de rótulos",
           "lung_trachea_bronchia" not in lote_py
           and "lung_trachea_bronchia" not in vigia_py)

    corpo = lote_py.split("def _uma_serie(")[1].split("\ndef ")[0]
    checar("o lote continua recolhendo os rótulos crus", "cruas=cruas" in corpo,
           "o `_ts` e o `_full` saem deles, e nao do torax")


def teste_falha_de_ambiente_nao_vira_falha_de_serie():
    secao("processar: ambiente sem TotalSegmentator recusa antes de tocar na série")
    ok, detalhe = L.pode_segmentar()
    checar("pode_segmentar responde", isinstance(ok, bool))
    checar("e diz o motivo quando não dá", ok or bool(detalhe), detalhe)

    tocou = []
    marcadores = dict((k, lambda *a, **kw: tocou.append(k))
                      for k in L.MARCADORES_EXIGIDOS)
    r = L.iniciar([{"uid": "X", "pasta": "p"}], marcadores=marcadores)
    if not ok:
        checar("com o runtime errado, recusa", not r.get("ok"))
        checar("marcada como falha de AMBIENTE", r.get("ambiente") is True)
        checar("e diz que nenhuma série foi marcada",
               "NENHUMA" in (r.get("erro") or ""), (r.get("erro") or "")[:60])
        checar("sem tocar em marcador nenhum", not tocou, str(tocou))
        checar("apontando o caminho que resolve",
               "bundle" in (r.get("erro") or "").lower())
    else:
        checar("neste runtime dá para segmentar — o teste não se aplica", True)

    r = L.iniciar([], marcadores=marcadores)
    checar("lista vazia não é barrada por ambiente", not r.get("ambiente"))


def teste_o_erro_da_serie_chega_na_tela():
    secao("processar: o erro da série sai no estado")
    with L._TRAVA:
        guardado = list(L._JOB["resultados"])
        L._JOB["resultados"] = [{"uid": "A", "erro": ""},
                                {"uid": "B", "erro": "nnUNet ficou sem memoria"}]
    try:
        e = L.estado()
        checar("estado expõe ultimo_erro", "ultimo_erro" in e)
        checar("e é o da série que falhou",
               e["ultimo_erro"] == "nnUNet ficou sem memoria", e.get("ultimo_erro"))
    finally:
        with L._TRAVA:
            L._JOB["resultados"] = guardado


def teste_fila_de_casos():
    secao("fila: enfileira em vez de recusar, e não duplica")
    with L._TRAVA:
        antes_job, antes_fila = dict(L._JOB), list(L._FILA)
        L._JOB.update({"rodando": True, "uid_atual": "1.2.A"})
        del L._FILA[:]
    try:
        b = L.enfileirar({"uid": "1.2.B", "cortes": 100})
        checar("com trabalho em curso, enfileira", b.get("enfileirada") is True)
        checar("e diz a posição", b.get("posicao") == 1, str(b.get("posicao")))
        L.enfileirar({"uid": "1.2.C", "cortes": 200})
        checar("a fila mantém a ordem",
               [x["uid"] for x in L.fila()] == ["1.2.B", "1.2.C"])

        r = L.enfileirar({"uid": "1.2.B", "cortes": 100})
        checar("série repetida não entra de novo", r.get("duplicada") is True)
        checar("nem a que está EM CURSO",
               L.enfileirar({"uid": "1.2.A"}).get("duplicada") is True)
        checar("a fila continua com duas", len(L.fila()) == 2)

        checar("o estado publica a fila", len(L.estado().get("fila") or []) == 2)

        r = L.cancelar()
        checar("cancelar descarta a fila", r.get("descartadas") == 2, str(r))
        checar("e diz isso no aviso", "fila" in (r.get("aviso") or ""))
        checar("a fila fica vazia", L.fila() == [])
    finally:
        with L._TRAVA:
            L._JOB.clear(); L._JOB.update(antes_job)
            del L._FILA[:]; L._FILA.extend(antes_fila)


def teste_os_dois_caminhos_gravam_os_mesmos_conjuntos():
    print(u"  -- os dois caminhos gravam os mesmos conjuntos --")
    import io
    vig = io.open(_componentes.fonte("app/radai_watcher.py"),
                  encoding="utf-8").read()
    lot = io.open(_componentes.fonte("app/radai_batch.py"),
                  encoding="utf-8").read()

    for nome, txt in ((u"o vigia", vig), (u"o «Rodar agora»", lot)):
        checar(u"%s monta a saida por `radai_output.Saida`" % nome,
               "radai_output" in txt and "Saida(" in txt)
        codigo = u"\n".join(l for l in txt.splitlines()
                            if not l.lstrip().startswith("#"))
        checar(u"%s monta o entregue pela porta unica (`full_e_oar`)" % nome,
               "sd.full_e_oar(" in codigo,
               u"a curadoria e o pos-processamento")
        checar(u"%s NAO cura nem agrupa por conta propria" % nome,
               "engine.curar(" not in codigo
               and "engine.para_oar(" not in codigo,
               u"seria o segundo pos-processamento que a v8.2 tirou")

    import re
    fora = []
    for arq in _componentes.nomes("app"):
        if not arq.endswith(".py") or arq in ("radai_output.py", "engine.py",
                                              "radai_rt.py"):
            continue
        txt = io.open(_componentes.fonte("app/" + arq), encoding="utf-8").read()
        for m in re.finditer(r"rotulo\s*=\s*[\"']STUDY_", txt):
            fora.append(arq)
    checar(u"nenhum modulo grava conjunto de estudo por fora de `radai_output`",
           not fora, ", ".join(sorted(set(fora))) or "nenhum")

    import radai_output
    for metodo in ("totalsegmentator_cru", "full_e_oar", "plugins",
                   "pelvicos"):
        checar(u"`radai_output.Saida` sabe gravar `%s`" % metodo,
               hasattr(radai_output.Saida, metodo))
        checar(u"e o «Rodar agora» o chama: %s" % metodo,
               (metodo + "(") in lot, u"faltava no caminho da tela")

    r = radai_output.relatorio(["ts", "full"])
    checar(u"o relatorio nomeia o que saiu", "ts" in r and "full" in r, r)
    checar(u"e nomeia o que nao saiu", "nv" in r and "cads" in r, r)


def _corpo_js(pag, nome):
    i = pag.find(u"function %s(" % nome)
    if i < 0:
        return u""
    j = pag.find(chr(10) + u"function ", i + 10)
    s = pag.find(u"</script>", i + 10)
    if j > 0 and (s < 0 or j < s):
        return pag[i:j]
    fim = s if s > 0 else len(pag)
    k = pag.find(chr(10) + u"}" + chr(10), i)
    return pag[i:(k + 2 if 0 < k < fim else fim)]


def _sem_comentario_js(txt):
    t = re.sub(u"(?s)/" + re.escape(u"*") + u".*?" + re.escape(u"*") + u"/",
               u"", txt or u"")
    t = re.sub(u"(?s)<!--.*?-->", u"", t)
    return chr(10).join(l for l in t.splitlines()
                        if not l.strip().startswith(u"//"))


def teste_o_localizar_filtra_a_lista():
    secao(u"a segunda busca saiu, e o ajudante dela ficou")
    import radai_batch as L
    pag = L.PAGINA
    checar(u"a caixa «localizar» saiu do passo 2",
           u'id="loc"' not in pag,
           u"«a busca ja foi feita no popup da tarefa 1»")
    codigo = _sem_comentario_js(pag)
    for nome in (u"locCasa", u"locLimpar", u"locNorm"):
        checar(u"  e `%s` nao e mais chamada nem declarada" % nome,
               (nome + u"(") not in codigo, u"sobrou no JS")
    checar(u"`dataBr` esta no escopo do modulo (coluna zero)",
           bool(re.search(u"(?m)^function dataBr" + chr(92) + u"(", pag)),
           u"declarada dentro de um callback nao existe fora dele")
    checar(u"  e a coluna Data a usa", u"dataBr(s.date)" in pag)
    corpo = _corpo_js(pag, u"marcar")
    checar(u"«incluir todas» ainda poupa a serie travada",
           u"'processando'" in corpo and u"porNoCarrinho(s" in corpo,
           corpo[:120])


def teste_o_carrinho_atravessa_a_troca_de_pasta():
    secao(u"o carrinho atravessa a troca de pasta")
    import radai_batch as L
    pag = L.PAGINA

    checar(u"ha uma chave estavel por serie", u"function chaveDe(" in pag)
    _c = pag.index(u"function chaveDe(")
    _corpo_chave = pag[_c:pag.index(u"function noCarrinho(", _c)]
    for parte in (u"s.pasta", u"s.uid", u"s.n"):
        checar(u"  e ela inclui `%s`" % parte, parte in _corpo_chave)
    checar(u"  e o separador e montado, nao escapado",
           u"String.fromCharCode(1)" in pag)

    i = pag.index(u"function varrer(")
    corpo = pag[i:pag.index(u"function modalidadeDe(", i)]
    checar(u"`varrer` nao zera a inclusao",
           not re.search(r"(?m)^(?!\s*//)\s*INCL\s*=\s*\{\s*\}", corpo),
           u"a linha que matava a escolha na troca de pasta")
    checar(u"  e a sugestao vale UMA VEZ por serie",
           u"if(VISTAS[" in corpo and u"VISTAS[k] = true" in corpo,
           u"sem isto, revarrer devolve ao carrinho o que a pessoa tirou")
    checar(u"  e a serie do carrinho e trocada pela recem-lida",
           u"CARRINHO[k] = s" in corpo,
           u"a situacao pode ter mudado desde que ela entrou")

    j = pag.index(u"function incluidas(")
    checar(u"`incluidas` devolve o carrinho, e nao a tabela a vista",
           u"carrinhoLista()" in pag[j:j + 260]
           and u"SERIES[" not in pag[j:j + 260])
    k = pag.index(u"function mandarParaAFila(")
    _corpo_env = pag[k:pag.index(u"function ", k + 10)]
    checar(u"e a escolha viaja DENTRO de cada serie (`payloadDaSerie`)",
           u"sel.map(payloadDaSerie)" in _corpo_env
           and u"topografias" not in _corpo_env,
           _corpo_env[:200])

    corpo_esc = _corpo_js(pag, u"escolhaDe")
    checar(u"o modo escolhido e guardado por CHAVE, e nao por indice",
           u"chaveDe(" in corpo_esc and u"ESCOLHA[k]" in corpo_esc,
           corpo_esc[:160])
    checar(u"  e a topografia por linha saiu com as caixas dela",
           u"function topoDe(" not in pag and u"data-topo-i" not in pag
           and u"function topoDasIncluidas(" not in pag)

    corpo_m = _corpo_js(pag, u"marcar")
    checar(u"«tirar as desta pasta» nao esvazia o carrinho inteiro",
           u"CARRINHO = {}" not in corpo_m and u"porNoCarrinho(s" in corpo_m)
    corpo_env = _sem_comentario_js(_corpo_js(pag, u"mandarParaAFila"))
    checar(u"o envio a fila limpa a selecao pela faxina que NAO pergunta",
           u"limparSelecao()" in corpo_env
           and u"esvaziarSelecao(" not in corpo_env
           and u"esvaziarCarrinho(" not in corpo_env
           and u"perguntar(" not in corpo_env,
           corpo_env[:200])
    corpo_limp = _sem_comentario_js(_corpo_js(pag, u"limparSelecao"))
    checar(u"  e a faxina nao abre dialogo nenhum",
           corpo_limp and u"perguntar(" not in corpo_limp
           and u"uiPainel(" not in corpo_limp and u"confirm(" not in corpo_limp,
           corpo_limp[:160])
    checar(u"  e a funcao que perguntava com o texto errado nao existe mais",
           u"function esvaziarCarrinho(" not in pag
           and u"Esvaziar o carrinho" not in _sem_comentario_js(pag))
    # GUARDA: Esvaziar seleção é ação rápida e tira só as séries da lista à vista.
    _corpo_e = _sem_comentario_js(_corpo_js(pag, u"esvaziarSelecao"))
    checar(u"  e quem esvazia o faz sem pergunta, só com as desta lista",
           u"perguntar(" not in _corpo_e and u"limparSelecao()" not in _corpo_e
           and u"porNoCarrinho(s, false)" in _corpo_e
           and u"CARRINHO = {}" not in _corpo_e, _corpo_e[:160])
    checar(u"  e a faxina nao toca na fila da barra",
           u"/api/fila" not in corpo_limp and u"radaiPipe" not in corpo_limp,
           corpo_limp[:160])
    _p = pag.index(u"function perguntar(")
    checar(u"  e `perguntar` cai no confirm nativo sem a biblioteca",
           u"window.uiPainel" in pag[_p:_p + 700]
           and u"confirm(" in pag[_p:_p + 700])

    import radai_batch as _b
    _op = _b.opcoes_da_tela("CT")
    _tasks = [t for t in _op["tasks"] if not t.get("motor")]
    checar(u"o payload leva a ficha de cada task",
           bool(_tasks) and all(t.get("ficha") for t in _tasks),
           u"%d de %d sem ficha"
           % (sum(1 for t in _tasks if not t.get("ficha")), len(_tasks)))
    checar(u"  e o selo de custo, com rotulo do servidor",
           all(t.get("custo") and t.get("custo_rotulo") for t in _tasks),
           u"rotulo digitado no JS seria a segunda fonte")
    _baldes = set(t["custo"] for t in _tasks)
    checar(u"  e os tres baldes de custo aparecem",
           _baldes == {"leve", "medio", "pesado"}, u", ".join(sorted(_baldes)))
    _por_nome = {t["task"]: t for t in _tasks}
    for _t, _fator in ((u"teeth", u"6×"), (u"oculomotor_muscles", u"3,5×")):
        _f = _por_nome.get(_t) or {}
        _vals = [r["val"] for r in (_f.get("ficha") or ())]
        checar(u"  `%s` diz quanto e' mais fina que a rotina" % _t,
               _fator in _vals, u"|".join(_vals))
    checar(u"  e ele NAO desabilita a caixa",
           (_por_nome.get(u"teeth") or {}).get("permitida") is not False,
           u"aviso virou impedimento")
    _te = [r for r in ((_por_nome.get(u"teeth") or {}).get("ficha") or ())
           if r["rot"] == u"no conjunto entregue"]
    checar(u"  e a linha do entregue mostra zero em vez de sumir",
           bool(_te) and _te[0]["val"] == u"0",
           u"ausente" if not _te else _te[0]["val"])
    import radai_phrases as _fr
    _ch = set(_fr.normalizar(l[0]) for l in _fr.TABELA)
    _sem = sorted(set(
        [t["custo_rotulo"] for t in _tasks if t.get("custo_rotulo")]
        + [r["rot"] for t in _tasks for r in (t.get("ficha") or ())]
        + [r["val"] for t in _tasks for r in (t.get("ficha") or ())
           if r.get("frase")]))
    _sem = [x for x in _sem if _fr.normalizar(x) not in _ch]
    checar(u"  e toda frase da ficha tem chave no dicionario",
           not _sem, u" | ".join(_sem[:4]))
    import radai_tasks as _rt
    _rot = [d["rotulo"] for d in _rt.CATALOGO
            if _fr.normalizar(d["rotulo"]) not in _ch]
    checar(u"  e todo rotulo do catalogo tem chave",
           not _rot, u" | ".join(_rot[:3]))

    import radai_review as _rv
    _servida = _rv.aplicar(pag)
    _ia = _servida.index(u'id="radai_rev_fronteira"')
    _ib = _servida.index(u'id="radai_rev_ok"')
    checar(u"a fronteira clinica esta no dialogo do INICIAR, uma vez so",
           _servida.count(u'id="radai_rev_fronteira"') == 1
           and u"sugestão não aprovada" in _servida[_ia:_ia + 400])
    checar(u"  e logo antes do botao que comeca a segmentar", _ia < _ib
           and u"rev-bt" in _servida[_ia:_ib], u"tarja=%d botao=%d" % (_ia, _ib))
    checar(u"  e a tarja velha saiu da tela", u"aviso clin" not in pag)
    _cod = _sem_comentario_js(pag)
    checar(u"o passo 3 «Andamento» saiu da tela",
           u'id="cx3"' not in pag and u'id="andamento"' not in pag
           and u"fetch('/api/lote/estado')" not in _cod,
           u"o andamento mora no card da barra")
    checar(u"  e o aviso de sair com lote rodando tambem",
           u"beforeunload" not in _cod and u"LOTE_RODANDO" not in _cod
           and u"Há um lote rodando" not in pag,
           u"«a fila sempre fica rodando, independente de onde estamos»")
    checar(u"  e fora de balao e de rodape",
           u"ui-balao" not in _servida[_ia:_ib]
           and u"rodape" not in _servida[_ia:_ib],
           u"atras de um clique e' a forma educada de remover")

    checar(u"o resumo diz quantas series e de quantas pastas",
           u'id="cartcx"' in pag and u"carrinhoRaizes()" in pag)
    p = pag.index(u"function pintarCarrinho(")
    corpo_c = _sem_comentario_js(pag[p:pag.index(chr(10) + u"function ", p + 10)])
    checar(u"  e o resumo nao mostra caminho nenhum",
           u"s.pasta" not in corpo_c and u"split(SEP)" not in corpo_c,
           corpo_c[:200])


def teste_a_tabela_agrupa_por_estudo():
    secao(u"a tabela agrupa por estudo -- sem a linha do estudo")
    import radai_batch as L
    pag = L.PAGINA
    checar(u"ha agrupamento por estudo", u"function gruposDeEstudo(" in pag)
    import radai_triage as TR
    import inspect
    fonte = inspect.getsource(TR._chave_do_exame)
    tela = _corpo_js(pag, u"estudoDe")
    for campo in (u"estudo", u"dir", u"pasta"):
        checar(u"  e `%s` esta nas DUAS pontas" % campo,
               campo in fonte and campo in tela)
    _cod = _sem_comentario_js(pag)
    checar(u"a linha do estudo saiu da tabela",
           u'<tr class="grp' not in pag and u"function cabecaDoEstudo(" not in pag,
           u"ela repetia nome e data da linha logo abaixo")
    for nome in (u"estudoMarcar", u"estudoDobrar", u"pintarCabecalhosDeEstudo",
                 u"GRUPO_DOBRADO"):
        checar(u"  e `%s` saiu junto" % nome, nome not in _cod)
    checar(u"nenhum `onclick` monta aspas duplas por JSON.stringify",
           not re.search(u'onclick="[^"]*' + re.escape(u"' + JSON.stringify"),
                         _cod),
           u"a aspa do JSON fecha o atributo no meio -- o botao nao faz nada")
    corpo = _corpo_js(pag, u"pintarTabela")
    checar(u"a ordem das linhas continua sendo a dos estudos",
           u"gruposDeEstudo()" in corpo and u"linhaDaSerie" in corpo)


def teste_os_tres_cards_e_o_turno_da_noite():
    secao(u"os dois cards do topo, e o turno da noite")
    import radai_batch as L
    pag = L.PAGINA
    for cid in (u"cd_add", u"cd_night"):
        checar(u"o card `%s` existe" % cid, (u'id="%s"' % cid) in pag)
    _cards = re.findall(u'<div class="rc-card([^"]*)" id="(cd_[a-z_]+)"', pag)
    _inertes = [i for c, i in _cards if u"acao" not in c]
    checar(u"  e todo card da fileira e uma ACAO",
           not _inertes, u", ".join(_inertes))
    _tags = dict((i, t) for t, i in re.findall(
        u'(<div class="rc-card[^"]*" id="(cd_[a-z_]+)"[^>]*>)', pag))
    for cid in (u"cd_add", u"cd_night"):
        t = _tags.get(cid, u"")
        checar(u"  o card `%s` entra no Tab e se anuncia como botao "
               u"(tabindex=0, role=button)" % cid,
               u'tabindex="0"' in t and u'role="button"' in t, t[:120])
    checar(u"  Enter e Espaco num card focado o acionam (um ouvinte so, "
           u"delegado)",
           u"closest('.rc-card.acao[role=\"button\"]')" in pag
           and u"ev.key !== ' '" in pag)
    checar(u"  e o foco no card se ve (:focus-visible)",
           u".rc-card.acao:focus-visible{" in pag)
    checar(u"o turno pede o ESTADO, e nao «alterne»",
           u"ligado:quero" in pag and u"NIGHT_ON" in pag,
           u"o corpo do POST tem de carregar o estado pedido")
    checar(u"  e quem chama pode dizer QUAL estado",
           u"arguments.length" in pag,
           u"a folha do turno manda `true` explicito; o clique nu no card "
           u"continua alternando, que e o unico caso em que ninguem disse")
    checar(u"  e a fila da direita repinta na hora",
           u"radaiFilaPintar(d)" in pag,
           u"15 s de barra sem o card leem-se como «o botao nao funcionou»")
    import radai_queue_state as F
    import inspect
    checar(u"e a rota existe no servidor",
           u'"/api/fila/overnight"' in inspect.getsource(F.montar))


def teste_o_cads_roda_no_rodar_agora():
    secao(u"o CADS roda tambem no Rodar agora")
    import radai_cads_engine as CM
    checar(u"a sequencia mora no motor, e nao no vigia",
           hasattr(CM, "contornar"))
    fonte = io.open(_componentes.fonte("app/radai_batch.py"),
                    encoding="utf-8").read()
    checar(u"a tela chama a mesma funcao", u"CM.contornar(" in fonte)
    corpo = fonte.split(u"def _uma_serie(")[1].split(u"\ndef ")[0]
    checar(u"o CADS vai antes do FULL so se alimentar o FULL (o motor diz)",
           u'_liga_por_omissao("cads")' in corpo
           and u"cads=cads_da_vez" in corpo, corpo[:0])
    checar(u"e o mesmo resultado vira o arquivo CADS_, sem rodar de novo",
           u"sd.cads(cads_da_vez)" in fonte)
    checar(u"a chave e a da serie (comparacao do PERSONALIZADO), e nao a da "
           u"estacao", u'_CFG.get("incluir_cads")' not in fonte
           and u'_mot.get("cads")' in corpo)
    vigia = io.open(_componentes.fonte("app/radai_watcher.py"),
                    encoding="utf-8").read()
    marca_antiga = u"radai_cads" + u"_in_"
    checar(u"e o vigia nao tem a copia antiga da sequencia do CADS",
           marca_antiga not in vigia)


def teste_o_nome_do_paciente_aparece_na_tela_e_so_nela():
    secao(u"o nome do paciente aparece na tela, e so nela")
    import radai_batch as LT

    casos = [(u"FANTOMA^JOAO^C^^", u"JOAO C FANTOMA"),
             (u"ISCA^PAULO^R B^^", u"PAULO R B ISCA"),
             (u"SOBRENOME", u"SOBRENOME"),
             (u"", u""), (None, u"")]
    for bruto, esperado in casos:
        checar(u"`%s` -> `%s`" % (bruto, esperado),
               LT._nome_de_pessoa(bruto) == esperado,
               repr(LT._nome_de_pessoa(bruto)))
    checar(u"o `^` do padrao nunca sobra na tela",
           u"^" not in LT._nome_de_pessoa(u"A^B^C^D^E"))

    checar(u"`PatientName` entra na lista de tags lidas",
           "PatientName" in LT._TAGS)
    checar(u"e a celula do paciente mostra o nome com o prontuario embaixo",
           u"s.nome?" in LT.PAGINA and u"esc(s.nome)" in LT.PAGINA)
    checar(u"  e o cabecalho do visor da serie mostra o nome tambem",
           u"['Paciente', s.nome || '']" in _corpo_js(LT.PAGINA,
                                                      u"abrirVisorDaSerie"))

    fonte = io.open(_componentes.fonte("app/radai_batch.py"), encoding="utf-8").read()
    corpo = re.sub(r"(?m)^\s*#.*$", "", fonte)
    checar(u"o rotulo do log continua sendo prontuario + serie",
           u'rotulo = "%s · %s" % (s.get("pid", "?"), s.get("curto", ""))'
           in corpo, u"o rotulo mudou de fonte")
    for alvo, onde in ((u'"nome"', u"o marcador `done`"),
                       (u"nome=", u"o acervo")):
        pass
    for trecho, quem in ((u'done = {"uid"', u"marcador done"),
                         (u"radai_archive.registrar_serie(", u"acervo")):
        i = corpo.find(trecho)
        checar(u"achei %s para conferir" % quem, i >= 0)
        if i >= 0:
            bloco = corpo[i:i + 700]
            checar(u"  %s nao leva o nome do paciente" % quem,
                   u'"nome"' not in bloco and u"nome=" not in bloco
                   and u'get("nome"' not in bloco,
                   bloco[:120])
    checar(u"nenhuma rota GET carrega o nome",
           not re.search(r'@app\.get\([^)]*nome', corpo))


def teste_lock_morto_nao_trava_a_serie_para_sempre():
    secao(u"lock morto nao trava a serie para sempre")
    import radai_batch as LT
    import time as _t

    velho = dict(LT._CFG)
    try:
        LT._CFG.clear()
        LT._CFG.update({"maquina": "ESTACAO_A"})
        serie = {"pasta": "P", "uid": "1.2.3"}

        def marc(estado, quem, min_parado):
            reg = {"machine": quem, "start": "2026-09-02 11:33:27",
                   "heartbeat": _t.time() - min_parado * 60}
            return {"has_marker": lambda p, u, k: k == "lock",
                    "read_marker": lambda p, u, k: reg,
                    "diagnostico": lambda p, u: (estado, reg)}

        d = LT._situacao(serie, marc("trabalhando", "ESTACAO_A", 2))
        checar(u"dono renovando ha 2 min: continua `processando`",
               d["situacao"] == "processando", str(d))

        d = LT._situacao(serie, marc("morto", "ESTACAO_A", 83))
        checar(u"processo morto desta maquina: `retomavel`",
               d["situacao"] == "retomavel", str(d))
        checar(u"  e vem marcada, porque quem esta na frente e o dono",
               d.get("minha") is True, str(d))
        checar(u"  e o texto diz que incluir RETOMA, e nao que esta rodando",
               u"retoma" in d["detalhe"] and u"processamento" not in d["detalhe"],
               d["detalhe"])
        checar(u"  e diz ha quanto tempo parou",
               u"sem sinal de vida" in d["detalhe"], d["detalhe"])

        d = LT._situacao(serie, marc("travado", "outra_maq", 40))
        checar(u"lock parado de OUTRA estacao: retomavel, mas nao marcada",
               d["situacao"] == "retomavel" and d.get("minha") is False, str(d))
        checar(u"  e o texto diz que incluir ASSUME a serie dela",
               u"ASSUME" in d["detalhe"], d["detalhe"])

        sem = {"has_marker": lambda p, u, k: k == "lock",
               "read_marker": lambda p, u, k: {"machine": "ESTACAO_A",
                                               "start": "11:33"}}
        checar(u"sem `diagnostico` injetado, volta ao comportamento antigo",
               LT._situacao(serie, sem)["situacao"] == "processando")
    finally:
        LT._CFG.clear()
        LT._CFG.update(velho)

    checar(u"a tela distingue `retomavel` de `processando`",
           u"s.situacao==='retomavel'" in LT.PAGINA)
    checar(u"  e so `processando` desabilita o botao",
           u"var trava = (s.situacao==='processando');" in LT.PAGINA)
    checar(u"  e a de outra estacao nao vem pre-incluida",
           u"s.situacao==='retomavel' && !s.minha" in LT.PAGINA)
    vigia = io.open(_componentes.fonte("app/radai_watcher.py"), encoding="utf-8").read()
    checar(u"o vigia injeta `diagnostico` nos marcadores",
           u'"diagnostico": _diagnostico_do_lock' in vigia)



def teste_a_serie_nao_ganha_tx_em_disco():
    secao("a serie nao ganha `_tx` em disco")
    import radai_sets as S

    checar("o infixo continua reconhecido para LEITURA",
           "TX_" in S.INFIXOS_DE_OUTRO_CONSUMIDOR,
           "sem isto, um `_TX_` que sobrou em pasta antiga seria lido como o "
           "ENTREGUE, e a previa mostraria o arquivo errado sem erro")

    cods = [c["cod"] for c in S.CONJUNTOS]
    checar("e `tx` nao e um dos conjuntos gravados", "tx" not in cods,
           ", ".join(cods))

    import glob
    import tempfile
    base = tempfile.mkdtemp(prefix="radai_tx_")
    try:
        antes = glob.glob(os.path.join(base, "RS_RadAI_TX_*"))
        checar("a pasta do fantoma comeca sem `_tx`", not antes)
        import engine as _M
        gravadores = [n for n in dir(_M)
                      if "torax" in n.lower() and n.startswith(("entregar",
                                                                "gravar",
                                                                "salvar"))]
        checar("o motor nao expoe gravador de torax", not gravadores,
               ", ".join(gravadores) or "nenhum")
        depois = glob.glob(os.path.join(base, "RS_RadAI_TX_*"))
        checar("e a pasta continua sem `_tx`", not depois,
               ", ".join(os.path.basename(x) for x in depois))
    finally:
        import shutil
        shutil.rmtree(base, ignore_errors=True)


def _esperar_thread(lista, segundos=5.0):
    import time
    fim = time.time() + segundos
    while time.time() < fim and not lista:
        time.sleep(0.01)
    return lista


def teste_o_dropdown_do_rodar_agora_executa_a_trava_das_categorias():
    secao(u"«Rodar agora»: os modos e os protocolos saem de radai_modes, e "
          u"a trava roda")
    import inspect
    import radai_modes as md
    opc = L.opcoes_da_tela("CT")
    checar(u"os tres modos, na ordem do seletor, e o de fabrica e o AUTO",
           [m["cod"] for m in opc.get("modos") or ()]
           == ["fast", "auto", "perso"]
           and opc.get("modo_de_fabrica") == "auto"
           and all(m.get("ajuda") for m in opc.get("modos") or ())
           and bool(opc.get("ajuda_dos_modos")),
           str([m.get("cod") for m in opc.get("modos") or ()]))
    cods = [p["cod"] for p in opc.get("protocolos") or ()]
    checar(u"os protocolos da TC, na ordem da spec 1.2",
           cods == ["cranio", "cabeca_pescoco", "torax_mama", "sbrt",
                    "abdome", "pelve", "coluna"], str(cods))
    checar(u"  e nada dos estudos da v8.2 na resposta",
           "estudos" not in opc and "motores" not in opc, str(sorted(opc)))
    _mr = L.opcoes_da_tela("MR")
    checar(u"  e os da RM sao os dela (Coluna e Abdomen)",
           [p["cod"] for p in _mr.get("protocolos") or ()]
           == ["coluna_rm", "abdome_rm"],
           str([p["cod"] for p in _mr.get("protocolos") or ()]))
    cp = [p for p in opc.get("protocolos") or () if p["cod"] == "cabeca_pescoco"]
    checar(u"o Cabeca e Pescoco avancado arrasta as cinco do FULL e liga os "
           u"niveis", bool(cp) and sorted(cp[0]["tasks"]) == sorted((
               "head_glands_cavities", "headneck_muscles",
               "headneck_bones_vessels", "head_muscles",
               "craniofacial_structures"))
           and cp[0]["motores"] == ["hnlnl", "cranio_ct"],
           str(cp[:1]))
    por = dict((t["task"], t) for t in opc.get("tasks") or ())
    checar(u"a orbita e os dentes sao tasks avulsas (fora de protocolo)",
           por.get("oculomotor_muscles", {}).get("protocolos") == []
           and por.get("teeth", {}).get("protocolos") == [],
           str([por.get(t, {}).get("protocolos")
                for t in ("oculomotor_muscles", "teeth")]))
    niv = por.get(L.CHAVE_DOS_NIVEIS) or {}
    checar(u"os niveis cervicais estao na coluna das tasks, como motor",
           niv.get("motor") is True and "cabeca_pescoco" in (
               niv.get("protocolos") or ()), str(niv)[:160])
    checar(u"  e so na TC", L.CHAVE_DOS_NIVEIS not in [
        t["task"] for t in _mr.get("tasks") or ()])
    _tk = [t for t in opc.get("tasks") or () if not t.get("motor")]
    _vels = list(opc.get("velocidades") or ())
    faltam = [t["task"] for t in _tk
              if not (t.get("rotulo") and "estruturas" in t
                      and t.get("alimenta") in ("full", "arquivo")
                      and isinstance(t.get("avisos"), list)
                      and (t.get("modelo") or {}).get("nome")
                      == u"TotalSegmentator"
                      and (t.get("modelo") or {}).get("task")
                      and "versao" in (t.get("modelo") or {})
                      and t.get("velocidade") in _vels
                      and t.get("datasets"))]
    checar(u"cada task leva a ficha do «?»: o que segmenta, o que alimenta, "
           u"avisos, velocidade e modelo de origem e versao",
           bool(_tk) and not faltam, str(faltam[:4]))
    checar(u"  e o que alimenta sai do registro: a `trunk_cavities` vai ao "
           u"FULL, a `lung_vessels` a um arquivo proprio",
           (por.get("trunk_cavities") or {}).get("alimenta") == "full"
           and (por.get("lung_vessels") or {}).get("alimenta") == "arquivo")
    checar(u"a base vem TRAVADA", (opc.get("base_item") or {}).get("travada")
           is True and opc.get("base") == (opc.get("base_item") or {}).get(
               "task"), str(opc.get("base")))
    checar(u"a regra que ligava a `abdominal_muscles` junto com a `breasts` "
           u"saiu: o servidor nao manda dependencia nenhuma",
           opc.get("ao_ligar") == {}, str(opc.get("ao_ligar")))
    comp = [(c["cod"], c.get("disponivel")) for c in opc.get("comparacao") or ()]
    checar(u"a comparacao: TS cru, NV, CADS e MOOSE, todos disponiveis na TC",
           comp == [("ts", True), ("nv", True), ("cads", True),
                    ("mse", True)], str(comp))
    comp_mr = [(c["cod"], c.get("disponivel"))
               for c in _mr.get("comparacao") or ()]
    checar(u"  e na RM so o TS cru (os tres modelos sao de TC), com o motivo",
           comp_mr == [("ts", True), ("nv", False), ("cads", False),
                       ("mse", False)]
           and all(c.get("porque_nao") for c in _mr["comparacao"][1:]),
           str(comp_mr))
    checar(u"  e cada uma diz se esta instalada e a licenca",
           all("instalado" in c and "licenca" in c
               for c in opc.get("comparacao") or ()))
    try:
        import engine
        achados = set(getattr(engine, "TASKS_DE_ACHADO", ()) or ())
    except Exception:
        achados = set()
    _arr = [(p["cod"], t) for p in opc.get("protocolos") or ()
            for t in p["tasks"] if t in achados]
    checar(u"nenhum protocolo arrasta achado (REGRA A)", not _arr, str(_arr))
    _ach = [t for t in _tk if t["task"] in achados]
    checar(u"  e as de achado continuam OFERECIDAS, com o selo e o aviso "
           u"(a chave da propria task e o ato da regra B)",
           bool(_ach) and all(t.get("achado") and any(
               u"ACHADO" in a for a in t.get("avisos") or ()) for t in _ach),
           str([t["task"] for t in _ach]))

    def _forjar(prot, fn=None):
        guard = (md.PROTOCOLOS, dict(md.PROT_POR_COD))
        try:
            md.PROTOCOLOS = tuple(list(md.PROTOCOLOS) + [prot])
            md.PROT_POR_COD[prot["cod"]] = prot
            try:
                (fn or L.opcoes_da_tela)("CT")
            except Exception as e:
                return "%s: %s" % (type(e).__name__, e)
            return ""
        finally:
            md.PROTOCOLOS = guard[0]
            md.PROT_POR_COD.clear()
            md.PROT_POR_COD.update(guard[1])
    _fantasma = {"cod": "forjado", "rotulo": u"Forjado", "modalidade": "CT",
                 "ajuda": u"isca", "motores": (),
                 "tasks": ("task_que_nao_existe_em_versao_nenhuma",)}
    _com_achado = {"cod": "forjado_achado", "rotulo": u"Forjado",
                   "modalidade": "CT", "ajuda": u"isca", "motores": (),
                   "tasks": ("trunk_cavities", "lung_nodules")}
    lev = _forjar(_fantasma)
    checar(u"protocolo apontando para o que nao existe PARA a tela",
           "task_que_nao_existe_em_versao_nenhuma" in lev,
           lev[:160] or u"passou calado -- a trava nao esta no caminho")
    lev = _forjar(_com_achado)
    checar(u"protocolo arrastando achado PARA a tela (REGRA A)",
           lev.startswith("AchadoSemPedido"), lev[:160] or u"passou calado")
    src = inspect.getsource(L.opcoes_da_tela)
    alvo = u"md.conferir_protocolos(cat, achados)"
    ns = dict(vars(L))
    exec(compile(src.replace(alvo, u"pass"), "<isca-opcoes>", "exec"), ns)
    checar(u"ISCA: sem `conferir_protocolos`, as duas tabelas forjadas passam "
           u"caladas (a checagem sabe reprovar)",
           alvo in src and _forjar(_fantasma, ns["opcoes_da_tela"]) == ""
           and _forjar(_com_achado, ns["opcoes_da_tela"]) == "")

    saiu = L._com_escolhas_da_tela({"series": [
        {"uid": "1.2.3", "pasta": "p", "modo": "PERSONALIZADO",
         "protocolos": ["torax_mama", "x", "coluna_rm"],
         "tasks": {"lung_nodules": 1, "abdominal_muscles": "0", "?": "talvez"},
         "comparacao": {"ts": 1, "nv": "1", "zz": 1},
         "oar_fora": "heart, bag_bowel", "estudos": ["torax"]},
        {"uid": "1.2.4"},
        {"uid": "1.2.5", "modo": "fast", "protocolos": ["torax_mama"],
         "tasks": {"lung_nodules": 1}},
        {"uid": "1.2.6", "modalidade": "MR", "modo": "perso",
         "protocolos": ["torax_mama", "abdome_rm"],
         "comparacao": {"ts": 1, "nv": 1}}]})
    p0, p1, p2, p3 = saiu
    checar(u"o PERSONALIZADO chega normalizado: protocolos da modalidade, "
           u"chaves 0/1, comparacao e o «x» do OAR",
           p0.get("modo") == "perso" and p0.get("protocolos") == ["torax_mama"]
           and p0.get("tasks") == {"lung_nodules": 1, "abdominal_muscles": 0}
           and p0.get("comparacao") == {"ts": 1, "nv": 1, "cads": 0, "mse": 0}
           and p0.get("oar_fora") == ["heart", "bag_bowel"], str(p0))
    checar(u"  e a escolha da v8.2 que veio junto sai, e fica o nome dela",
           "estudos" not in p0 and p0.get("legado_v82") == ["estudos"],
           str(p0.get("legado_v82")))
    checar(u"serie sem modo e AUTO (spec T-R), sem lista nenhuma",
           p1.get("modo") == "auto" and not any(
               k in p1 for k in ("protocolos", "tasks", "comparacao",
                                 "oar_fora")), str(p1))
    checar(u"o FAST nao leva protocolo nem chave (nenhuma lista vale nele)",
           p2.get("modo") == "fast" and "tasks" not in p2
           and "protocolos" not in p2, str(p2))
    checar(u"na RM o protocolo de TC cai, e NV/CADS/MOOSE ficam em 0",
           p3.get("protocolos") == ["abdome_rm"]
           and p3.get("comparacao") == {"ts": 1, "nv": 0, "cads": 0, "mse": 0},
           str(p3))
    checar(u"e o protocolo Torax / Mama chega ao motor (`torax_pedido`)",
           L.torax_pedido(p0) is True and L.torax_pedido(p1) is None
           and L.torax_pedido(p2) is None)

    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        app = FastAPI()
        L.montar(app, {"tasks": ["total"], "device": "cpu"})
        r = TestClient(app).get("/api/lote/opcoes")
        d = r.json() if r.status_code == 200 else {}
        checar(u"/api/lote/opcoes responde", r.status_code == 200,
               str(r.status_code))
        checar(u"com os mesmos protocolos da funcao",
               [p["cod"] for p in (d.get("protocolos") or ())] == cods,
               str([p["cod"] for p in (d.get("protocolos") or ())]))
    except ImportError as e:
        checar(u"/api/lote/opcoes responde (fastapi ausente)", True, str(e))
    checar(u"a pagina busca as opcoes no servidor",
           "/api/lote/opcoes" in L._pagina(), u"isto mede o texto da pagina")


def teste_o_modo_da_tela_decide_e_nao_a_lista_do_config():
    secao(u"o modo da serie decide, e nao a lista do config")
    import radai_modes as _md
    q = L.quem_decide_as_tasks
    checar(u"serie SEM modo com lista do chamador: a lista decide (C5)",
           q(["total_v3"], {}) == "lista" and q(["total_v3"], {"modo": ""})
           == "lista")
    checar(u"serie COM modo: o modo decide, apesar da lista",
           all(q(["total_v3"], {"modo": m}) == "modo"
               for m in ("fast", "auto", "perso")))
    checar(u"sem lista e sem modo: o modo (AUTO) decide", q([], {}) == "modo")
    sem = L._com_escolhas_da_tela({"series": [{"uid": "1.2.3"}]})
    checar(u"a serie da tela sem escolha sai AUTO, e o modo decide",
           sem[0].get("modo") == "auto" and q(["total_v3"], sem[0]) == "modo",
           str(sem[0]))
    corpo = L._com_escolhas_da_tela({"series": [{"uid": "1.2.3"},
                                                {"uid": "1.2.4",
                                                 "modo": "perso"}],
                                     "modo": "fast"})
    checar(u"o modo do CORPO e o recuo, e o da serie vence",
           [s.get("modo") for s in corpo] == ["fast", "perso"],
           str([s.get("modo") for s in corpo]))
    checar(u"valor desconhecido e AUTO, e nunca FAST (o FAST entrega MENOS)",
           L._com_escolhas_da_tela({"series": [{"modo": "completo"}]})[0]
           .get("modo") == "auto")

    base = _md.base_de("CT")
    t_auto, o_auto = L.tasks_iniciais({"modo": "auto"}, ["total_v3"])
    t_fast, o_fast = L.tasks_iniciais({"modo": "fast"})
    t_lista, o_lista = L.tasks_iniciais({}, ["total_v3", "lung_vessels"])
    t_perso, o_perso = L.tasks_iniciais({
        "modo": "perso", "protocolos": ["torax_mama"],
        "tasks": {"abdominal_muscles": 0, "lung_nodules": 1}})
    _fam = lambda ts: set(__import__("radai_tasks").familia_da_task(t)
                          for t in ts)
    checar(u"AUTO e FAST rodam SO a base antes da anatomia",
           len(t_auto) == 1 and len(t_fast) == 1
           and _fam(t_auto) == _fam([base]) and o_auto == "auto"
           and o_fast == "fast", u"%s %s" % (t_auto, t_fast))
    checar(u"a lista do chamador roda a lista", o_lista == "lista"
           and "lung_vessels" in t_lista, str(t_lista))
    checar(u"o PERSONALIZADO roda o protocolo e as chaves, e a chave VENCE",
           o_perso == "perso" and "trunk_cavities" in t_perso
           and "breasts" in t_perso and "abdominal_muscles" not in t_perso,
           str(t_perso))
    checar(u"  e o achado LIGADO pela chave roda — o ato declarado da regra B",
           "lung_nodules" in t_perso, str(t_perso))
    checar(u"a conferencia anuncia o mesmo que o motor monta",
           tuple(L.tasks_previstas({"modo": "perso",
                                    "protocolos": ["torax_mama"],
                                    "tasks": {"abdominal_muscles": 0,
                                              "lung_nodules": 1}}))
           == tuple(t_perso))
    t_m1, _o = L.tasks_iniciais({"modo": "perso", "tasks": {"breasts": 1}})
    t_m2, _o = L.tasks_iniciais({"modo": "perso",
                                 "tasks": {"breasts": 1,
                                           "abdominal_muscles": 0}})
    checar(u"a `breasts` ligada a mao NAO arrasta mais a `abdominal_muscles`",
           "breasts" in t_m1 and "abdominal_muscles" not in t_m1, str(t_m1))
    checar(u"  e a chave dela em 0 vence (so a glandula)",
           "breasts" in t_m2 and "abdominal_muscles" not in t_m2, str(t_m2))

    dep = L.tasks_depois_da_base
    checar(u"FAST no torax: a cavidade, a glandula e o derrame, nessa ordem "
           u"(a `abdominal_muscles` saiu do FAST)",
           list(dep("fast", ("torax",), None, "CT"))
           == ["trunk_cavities", "breasts", "pleural_pericard_effusion"],
           str(dep("fast", ("torax",), None, "CT")))
    checar(u"FAST sem torax, com coracao >= 100 cm3: a `trunk_cavities`",
           tuple(dep("fast", ("abdome",), 150.0, "CT")) == ("trunk_cavities",)
           and tuple(dep("fast", ("abdome",), 50.0, "CT")) == ())
    checar(u"FAST na pelve pura e no cranio: so a base",
           tuple(dep("fast", ("pelve",), None, "CT")) == ()
           and tuple(dep("fast", ("cabeca_pescoco",), None, "CT")) == ())
    checar(u"AUTO na pelve: a `trunk_cavities` (a Bag_Bowel, spec 1.3)",
           tuple(dep("auto", ("pelve",), None, "CT")) == ("trunk_cavities",))
    checar(u"AUTO no torax: a tabela por topografia (a do vigia)",
           tuple(dep("auto", ("torax",), None, "CT"))
           == tuple(_md.tasks_da_topografia(("torax",), "CT")[1:]))
    checar(u"PERSONALIZADO e lista: a anatomia nao acrescenta nada",
           tuple(dep("perso", ("torax",), None, "CT")) == ()
           and tuple(dep("lista", ("torax",), None, "CT")) == ())
    _velha = dict(_md.TASKS_DO_FAST)
    try:
        _md.TASKS_DO_FAST[_md.TORAX] = ("abdominal_muscles", "breasts",
                                        "trunk_cavities")
        _ord = list(dep("fast", ("torax",), None, "CT"))
    finally:
        _md.TASKS_DO_FAST.clear()
        _md.TASKS_DO_FAST.update(_velha)
    checar(u"  isca: a tabela editada fora de ordem sai na ordem do FAST",
           _ord.index("breasts") < _ord.index("abdominal_muscles"), str(_ord))

    achados = ("lung_nodules",)
    try:
        _md.TASKS_DO_FAST[_md.TORAX] = tuple(_velha[_md.TORAX]) + (
            "lung_nodules",)
        lev = ""
        try:
            dep("fast", ("torax",), None, "CT", achados=achados)
        except Exception as e:
            lev = type(e).__name__
    finally:
        _md.TASKS_DO_FAST.clear()
        _md.TASKS_DO_FAST.update(_velha)
    checar(u"achado forjado na tabela do FAST LEVANTA (origem FAST)",
           lev == "AchadoSemPedido", lev or u"passou calado")
    _tab = _md.TASKS_POR_TOPOGRAFIA
    _vt = _tab.get("torax")
    try:
        _tab["torax"] = tuple(_vt) + ("lung_nodules",)
        lev = ""
        try:
            dep("auto", ("torax",), None, "CT", achados=achados)
        except Exception as e:
            lev = type(e).__name__
    finally:
        _tab["torax"] = _vt
    checar(u"achado forjado na tabela do AUTO LEVANTA (origem ANATOMIA)",
           lev == "AchadoSemPedido", lev or u"passou calado")
    _pr = _md.PROT_POR_COD["torax_mama"]
    _tv = _pr["tasks"]
    try:
        _pr["tasks"] = tuple(_tv) + ("lung_nodules",)
        lev = ""
        try:
            L.tasks_do_perso({"modo": "perso", "modalidade": "CT",
                              "protocolos": ("torax_mama",), "tasks": {}},
                             achados=achados)
        except Exception as e:
            lev = type(e).__name__
    finally:
        _pr["tasks"] = _tv
    checar(u"protocolo que arrasta achado LEVANTA (origem PROTOCOLO)",
           lev == "AchadoSemPedido", lev or u"passou calado")
    try:
        _md.tasks_do_modo("completo", "CT", ("torax",))
        checar(u"`tasks_do_modo('completo')` recusa (o Completo saiu)", False,
               u"devolveu uma lista")
    except ValueError:
        checar(u"`tasks_do_modo('completo')` recusa (o Completo saiu)", True)
    for _reg, _mod in (((_md.TORAX, _md.ABDOME), "CT"),
                       ((_md.CABECA_PESCOCO,), "MR")):
        _velho = _md.tasks_do_modo(_md.PADRAO, _mod, _reg)
        _hoje = _md.tasks_da_topografia(_reg, _mod)
        checar(u"`tasks_do_modo(PADRAO, %s, %s)` e `tasks_da_topografia`, na "
               u"letra" % (_mod, u"+".join(_reg)), tuple(_velho) == tuple(_hoje),
               u"%r x %r" % (_velho, _hoje))
    _isca = tuple(t for t in _md.tasks_da_topografia(("torax",), "CT")
                  if t != _md.BASE_DA_MODALIDADE["CT"])
    checar(u"  isca: sem a base da modalidade a comparacao reprova",
           _isca != tuple(_md.tasks_do_modo(_md.PADRAO, "CT", ("torax",))),
           str(_isca))


def teste_o_nv_nao_liga_por_omissao_em_caminho_nenhum():
    secao(u"NV/CADS/MOOSE: so por pedido da serie, no PERSONALIZADO")
    criterio = L._liga_por_omissao("nv")
    checar(u"o NV nao alimenta a entrega, entao o criterio diz DESLIGADO",
           criterio is False,
           u"medido de engine.motores_que_alimentam(): %r" % (criterio,))
    guardado = dict(L._CFG)
    try:
        L._CFG.update({"incluir_vista": 1, "incluir_nv": 1,
                       "incluir_cads": 1, "incluir_moose": 1,
                       "incluir_hnlnl": 1})
        casos = (({}, u"serie sem escolha (AUTO)"),
                 ({"modo": "auto"}, u"AUTO"),
                 ({"modo": "fast"}, u"FAST"),
                 ({"modo": "perso"}, u"PERSONALIZADO sem comparacao"))
        for serie, nome in casos:
            m, o = L.motores_da_serie(
                L._com_escolhas_da_tela({"series": [serie]})[0],
                incluir_nv=True)
            checar(u"%s: nenhum motor de comparacao, com a chave velha e o "
                   u"`incluir_nv` do chamador ligados" % nome,
                   not (m.get("nv") or m.get("cads") or m.get("mse")),
                   u"%s %s" % (o, m))
        m, o = L.motores_da_serie(L._com_escolhas_da_tela({"series": [
            {"modo": "perso", "comparacao": {"nv": 1, "mse": 1}}]})[0])
        checar(u"o PERSONALIZADO com a chave: roda o que a serie pediu",
               o == "perso" and m.get("nv") is True and m.get("mse") is True
               and m.get("cads") is False, str(m))
        m, o = L.motores_da_serie(L._com_escolhas_da_tela({"series": [
            {"modo": "perso", "modalidade": "MR",
             "comparacao": {"nv": 1, "cads": 1, "mse": 1}}]})[0])
        checar(u"  e numa RM, nenhum (os tres sao modelos de TC)",
               not (m.get("nv") or m.get("cads") or m.get("mse")), str(m))
    finally:
        L._CFG.clear()
        L._CFG.update(guardado)
    fonte = lote_py_txt()
    checar(u"a funcao que lia a chave da estacao saiu, e ninguem a chama",
           u"_nv_da_estacao(" not in fonte
           and u"def motores_da_estacao(" not in fonte)


def _varrer_pela_casca(pasta, uso="lote"):
    import radai_varrer
    d = radai_varrer.iniciar(uso, pasta, dias=0, em_segundo_plano=False)
    fora = dict(d.get("extra") or {})
    fora["series"] = list(d.get("linhas") or [])
    if d.get("erro"):
        fora["erro"] = d["erro"]
    return fora


def teste_a_coluna_de_modalidade_roteia_os_plugins_da_linha():
    secao(u"a coluna TC/RM: a lista, o dropdown e a triagem")
    import radai_modes as md

    base = tempfile.mkdtemp(prefix="radai_t_mod_")
    try:
        _serie(os.path.join(base, "ct"), 1, 24, 3.0, "B30f", "TC TORAX")
        _serie(os.path.join(base, "mr"), 2, 24, 3.0, "", "RM PELVE",
               modalidade="MR")

        vistas = L.varrer(base, modalidades=L.MODALIDADES_DA_TELA,
                          min_cortes=20, incluir_zips=True)
        mods = sorted(str(s.get("modalidade") or "") for s in vistas)
        checar(u"a varredura da tela lista CT E MR", mods == ["CT", "MR"],
               u"veio %s" % (mods or u"nada"))
        checar(u"e cada serie carrega a propria modalidade",
               bool(vistas) and all(s.get("modalidade") for s in vistas),
               u"serie sem o campo faz a coluna mostrar um travessao")

        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from fastapi import FastAPI
                from fastapi.testclient import TestClient
            app = FastAPI()
            L.montar(app, {"tasks": ["total"], "device": "cpu",
                           "min_cortes": 20})
            cli = TestClient(app)
            sr = _varrer_pela_casca(base).get("series") or []
            rota = sorted(str(s.get("modalidade") or "") for s in sr)
            checar(u"a varredura da tela (uso lote) devolve as duas "
                   u"modalidades", rota == ["CT", "MR"],
                   u"veio %s -- a varredura chama varrer() sem `modalidades`?"
                   % (rota or u"nada"))

            ct = cli.get("/api/lote/opcoes?modalidade=CT").json()
            mr = cli.get("/api/lote/opcoes?modalidade=MR").json()
            sem = cli.get("/api/lote/opcoes").json()
            cods_ct = [c["cod"] for c in (ct.get("protocolos") or ())]
            cods_mr = [c["cod"] for c in (mr.get("protocolos") or ())]
            checar(u"a rota responde diferente para CT e para MR",
                   cods_ct != cods_mr,
                   u"CT=%s | MR=%s" % (cods_ct, cods_mr))
            checar(u"e a de RM traz os protocolos dela (Coluna e Abdomen)",
                   cods_mr == ["coluna_rm", "abdome_rm"], str(cods_mr))
            checar(u"que nao aparecem na de TC",
                   not (set(cods_mr) & set(cods_ct)), str(cods_ct))
            _cmp_mr = dict((c["cod"], c.get("disponivel"))
                           for c in (mr.get("comparacao") or ()))
            _cmp_ct = dict((c["cod"], c.get("disponivel"))
                           for c in (ct.get("comparacao") or ()))
            checar(u"e a Comparacao de Modelos so vale na TC",
                   all(_cmp_ct.get(k) for k in ("nv", "cads", "mse"))
                   and not any(_cmp_mr.get(k) for k in ("nv", "cads", "mse")),
                   u"CT=%s | MR=%s" % (_cmp_ct, _cmp_mr))
            import radai_tasks as _K
            checar(u"a base muda junto: a de TC na TC, a de RM na RM",
                   ct.get("base") == _K.BASES_CT[0]
                   and mr.get("base") == _K.BASES_MR[0],
                   u"CT=%r MR=%r" % (ct.get("base"), mr.get("base")))
            checar(u"e sem o parametro a resposta e a de CT -- era o que a "
                   u"tela recebia",
                   [c["cod"] for c in (sem.get("protocolos") or ())]
                   == cods_ct)
        except ImportError as e:
            checar(u"as rotas respondem (fastapi ausente)", True, str(e))
    finally:
        shutil.rmtree(base, ignore_errors=True)

    _ch = {"lung_nodules": 1, "total_mr": 1}
    corpo = {"series": [{"uid": "1.2.3", "pasta": "p", "modalidade": "CT",
                         "modo": "perso", "tasks": dict(_ch)},
                        {"uid": "4.5.6", "pasta": "p", "modalidade": "MR",
                         "modo": "perso", "tasks": dict(_ch)}]}
    saiu = L._com_escolhas_da_tela(corpo)
    da_ct = L.tasks_previstas(saiu[0], ("total",))
    da_mr = L.tasks_previstas(saiu[1], ("total",))
    checar(u"a serie de TC nao recebe a biblioteca de RM",
           "total_mr" not in da_ct, str(da_ct))
    checar(u"e a de RM roda a `total_mr`", "total_mr" in da_mr, str(da_mr))
    checar(u"e nao recebe task de TC nenhuma",
           not (set(da_mr) - {"total_mr"}), str(da_mr))
    checar(u"as duas linhas, com as MESMAS caixas marcadas, rodam coisas "
           u"diferentes", tuple(da_ct) != tuple(da_mr),
           u"CT=%s | MR=%s" % (da_ct, da_mr))

    sem_mod = L._com_escolhas_da_tela(
        {"series": [{"uid": "7.8.9", "pasta": "p"}]})
    import radai_tasks as _K2
    prev = L.tasks_previstas(sem_mod[0], (_K2.BASES_CT[0],))
    checar(u"serie sem modalidade roda como TC -- e o `title` da celula diz "
           u"isso", bool(prev) and _K2.modalidade_da_base(prev[0]) == "CT",
           str(prev))

    import radai_languages as lg
    import radai_phrases as ph
    d = ph.construir()
    checar(u"«TC» vira «CT» em ingles e «TDM» em frances",
           d["en"].get(u"TC") == u"CT" and d["fr"].get(u"TC") == u"TDM",
           u"en=%r fr=%r" % (d["en"].get(u"TC"), d["fr"].get(u"TC")))
    checar(u"«RM» vira «MR» em ingles e «IRM» em frances",
           d["en"].get(u"RM") == u"MR" and d["fr"].get(u"RM") == u"IRM",
           u"en=%r fr=%r" % (d["en"].get(u"RM"), d["fr"].get(u"RM")))
    checar(u"e em espanhol/italiano a ausencia e o certo: sao as mesmas letras",
           d["es"].get(u"TC") is None and d["it"].get(u"RM") is None)
    checar(u"o rotulo da coluna reusa «Modalidade», que a suite ja usa para "
           u"este campo", bool(d["en"].get(u"Modalidade")),
           str(d["en"].get(u"Modalidade")))
    checar(u"e nenhuma das duas esta em NAO_TRADUZIR",
           u"TC" not in lg.NAO_TRADUZIR and u"RM" not in lg.NAO_TRADUZIR)
    aviso = (u"o cabeçalho desta série não declarou a modalidade; "
             u"o processamento vai seguir como TC")
    checar(u"o aviso de modalidade ausente esta na pagina, byte a byte",
           aviso in L._pagina(),
           u"isto mede o texto da pagina: chave partida com `+` nao casa")
    faltam = [c for c in ph.CODIGOS if not d[c].get(aviso)]
    checar(u"e ele tem os onze idiomas", not faltam,
           u"faltam: %s" % u", ".join(faltam))

    mesmo = [{"uid": "ct", "estudo": "E1", "modalidade": "CT",
              "cortes": 120, "espessura_mm": 3.0, "axial": True},
             {"uid": "mr", "estudo": "E1", "modalidade": "MR",
              "cortes": 140, "espessura_mm": 3.0, "axial": True}]
    fora = {x["uid"]: x for x in T.escolher_para_contorno(mesmo)}
    checar(u"a RM nao e pre-incluida como «TC de simulacao»",
           not fora["mr"]["sugerida"],
           fora["mr"]["porque_sugerida"][:90] or u"(sem motivo)")
    checar(u"e a TC do mesmo estudo continua sendo",
           bool(fora["ct"]["sugerida"]),
           u"tirar a RM do balde nao pode tirar a TC junto")
    mudo = [{"uid": "x", "estudo": "E2", "cortes": 120,
             "espessura_mm": 3.0, "axial": True}]
    checar(u"serie sem o campo continua sendo sugerida -- o vigia nao o le",
           bool(T.escolher_para_contorno(mudo)[0]["sugerida"]),
           u"«nao sei» nao pode virar recusa")

    pag = L._pagina()
    i = pag.find(u"<tr><th>Paciente</th>")
    cab = pag[i:pag.find(u"</tr>", i)] if i >= 0 else u""
    p_data = cab.find(u"<th>Data</th>")
    p_mod = cab.find(u"<th>Modalidade</th>")
    p_cor = cab.find(u"<th>Cortes</th>")
    checar(u"a coluna esta entre a data e os cortes",
           0 <= p_data < p_mod < p_cor,
           u"isto mede o texto da pagina | data=%d mod=%d cortes=%d"
           % (p_data, p_mod, p_cor))
    n_th = cab.count(u"<th>")
    checar(u"e os dois `colspan` acompanham as %d colunas" % n_th,
           (u"colspan=%d " % n_th) in pag and (u'colspan="%d"' % n_th) in pag,
           u"colspan desalinhado quebra a previa e a linha do vazio")

    import engine as _eng
    import radai_tasks as _rt
    de_rm = [c["task"] for c in _rt.CATALOGO
             if str(c.get("modalidade") or "CT").upper() == "MR"]
    checar(u"`total_mr` continua sendo a BASE da RM", md.base_de("MR") == "total_mr",
           str(md.base_de("MR")))
    checar(u"e ha task de RM no catalogo (a lista cresceu, e pode crescer)",
           len(de_rm) >= 1, str(de_rm))
    for _mod in ("CT", "MR"):
        checar(u"a guarda de %s concorda com o TS_MAP sobre a base" % _mod,
               L.base_alimenta_o_entregue(_mod)
               == bool(_eng.alimenta_o_entregue(md.base_de(_mod))),
               u"tela=%r motor=%r" % (L.base_alimenta_o_entregue(_mod),
                                      _eng.alimenta_o_entregue(md.base_de(_mod))))
    todas_rm = set()
    for _reg in md.TOPOGRAFIAS:
        todas_rm |= set(md.tasks_da_topografia(
            (_reg,), "MR",
            permitidas=getattr(_eng, "TASKS_PERMITIDAS", None),
            achados=getattr(_eng, "TASKS_DE_ACHADO", ()),
            catalogo=_rt.CATALOGO))
    todas_rm |= set(L.tasks_iniciais(
        {"modo": "perso", "modalidade": "MR",
         "tasks": dict((d["task"], 1) for d in _rt.CATALOGO)})[0])
    _de_ct = [t for t in todas_rm
              if str((dict((d["task"], d) for d in _rt.CATALOGO).get(t) or {})
                     .get("modalidade") or "CT").upper() != "MR"]
    checar(u"toda task alcancavel numa RM e de RM, em todo modo e regiao",
           not _de_ct, str(sorted(_de_ct)))
    _ach = set(getattr(_eng, "TASKS_DE_ACHADO", ()))
    _padrao_rm = set()
    for _reg in md.TOPOGRAFIAS:
        _padrao_rm |= set(md.tasks_da_topografia(
            (_reg,), "MR",
            permitidas=getattr(_eng, "TASKS_PERMITIDAS", None),
            achados=tuple(_ach), catalogo=_rt.CATALOGO))
    checar(u"a tabela do vigia numa RM nao traz achado nenhum",
           not (_padrao_rm & _ach), str(sorted(_padrao_rm & _ach)))
    checar(u"e ela NAO tem como reprovar uma TC: a base dela e a `total`",
           L.base_alimenta_o_entregue("CT"),
           u"guarda que reprova o certo e pior que guarda nenhuma")
    _todo = lote_py_txt().split(u"def _uma_serie(")[1]
    _corpo = _todo.split(chr(10) + u"def ")[0]
    _g = _corpo.find(u"if not base_alimenta_o_entregue(")
    _r = _corpo.find(u"engine.run_ts_task(")
    checar(u"e e consultada ANTES do primeiro `run_ts_task`", 0 <= _g < _r,
           u"guarda=%d run_ts_task=%d" % (_g, _r))


import radai_output as _RO_DE_VERDADE
_ALVO_DE_VERDADE = _RO_DE_VERDADE.Saida._alvo


def _rs_dublado(saida, destino, rs_name, cods=("oar",)):
    import radai_sets as _RS_d
    saida.destino, saida.rs_name = str(destino), str(rs_name)
    saida._alvo = lambda infixo: _ALVO_DE_VERDADE(saida, infixo)
    if not os.path.isdir(saida.destino):
        return []
    for cod in cods:
        alvo = saida._alvo(_RS_d.POR_COD[cod]["infixo"])
        try:
            with io.open(alvo, "wb") as f:
                f.write(b"RTSTRUCT dublado")
        except OSError:
            continue
        if cod not in saida.gravados:
            saida.gravados.append(cod)
    return list(saida.gravados)


class _SaidaEspia(object):
    anotado = {}
    atual = {"uid": ""}

    def __init__(self, engine, stage, destino, rs_name, **k):
        self.gravados = []
        self._rs = rs_name
        self._destino = destino
        self._reg = _SaidaEspia.anotado.setdefault(
            _SaidaEspia.atual["uid"], {"chamadas": [], "full_e_oar": None})

    def full_e_oar(self, cruas, **k):
        self._reg["full_e_oar"] = dict(k)
        self._reg["chamadas"].append("full_e_oar")
        modo = k.get("modo") or "auto"
        if modo == "fast":
            alvo = self._rs.replace("RS_RadAI_", "RS_RadAI_FAST_")
            _rs_dublado(self, self._destino, self._rs, ("fast",))
        else:
            alvo = self._rs
            _rs_dublado(self, self._destino, self._rs, ("oar", "full"))
        return {"estruturas": ["Liver_ai"], "entregue": alvo,
                "oar_fora": list(k.get("oar_fora") or []),
                "segundos": 1.0, "etapas": [], "modo": modo}

    def _alvo(self, infixo):
        return os.path.join(u"espia", self._rs.replace(
            u"RS_RadAI_", u"RS_RadAI_" + infixo))

    def __getattr__(self, nome):
        if nome.startswith(u"__") or nome.startswith(u"meta_do_"):
            raise AttributeError(nome)
        reg = self.__dict__.get("_reg")

        def _anota(*a, **k):
            if reg is not None:
                reg["chamadas"].append(nome)
            return None
        return _anota


def _dublar_o_motor(E, dublados, run_ts, regioes, base_dir=None):
    import SimpleITK as sitk
    import radai_output as RO
    import radai_cads_engine as CM
    import radai_moose_engine as MM
    import radai_topography as TP

    def _dublar(obj, nome, novo):
        dublados.append((obj, nome, getattr(obj, nome)))
        setattr(obj, nome, novo)

    def _ref():
        img = sitk.Image(8, 8, 8, sitk.sitkInt16)
        img.SetSpacing((0.7, 0.7, 3.0))
        return img
    _dublar(E, "copy_sorted", lambda arqs, stage: None)
    _dublar(E, "load_sitk", lambda stage: _ref())
    _dublar(E, "_resolve_device", lambda d: "cpu")
    _dublar(E, "run_ts_task", run_ts)
    _dublar(TP, "anatomia_da_base", regioes)
    _dublar(RO, "Saida", _SaidaEspia)
    _dublar(L, "_rodar_nv", lambda *a, **k: (_SaidaEspia.anotado.setdefault(
        _SaidaEspia.atual["uid"], {"chamadas": []})["chamadas"].append(
            "rodou_nv") or {"liver_nv": 1}))
    _dublar(CM, "contornar", lambda *a, **k: (_SaidaEspia.anotado.setdefault(
        _SaidaEspia.atual["uid"], {"chamadas": []})["chamadas"].append(
            "rodou_cads") or {"colon": 1}))
    _dublar(MM, "contornar", lambda *a, **k: (_SaidaEspia.anotado.setdefault(
        _SaidaEspia.atual["uid"], {"chamadas": []})["chamadas"].append(
            "rodou_mse") or {"heart_atrium_left": 1}))


def teste_o_modo_e_da_serie_e_chega_ao_motor():
    secao(u"a escolha e da serie, e chega ao motor e a gravacao")
    import inspect
    import json
    import engine as E

    base = tempfile.mkdtemp(prefix="radai_t_modo_")
    estudo = os.path.join(base, "PAC", "ESTUDO")
    uids = {}
    for cod, n in (("sem", 2), ("fast", 3), ("auto", 4), ("perso", 5)):
        uids[cod] = _serie(os.path.join(estudo, "S%d" % n), n, 8, 3.0, "B30f",
                           "TORAX %s" % cod)
    pedidas, dones = {}, {}
    dublados = []

    def _ts(ref, t, **k):
        pedidas.setdefault(_SaidaEspia.atual["uid"], []).append(t)
        if k.get("cruas") is not None:
            k["cruas"][t] = {"liver": 1}
        return {"liver_%s" % t: 1}

    def _regioes(masks, grade, cruas=None, motor=None):
        return {"regioes": ("abdome", "torax"), "laudo": [u"dublada"],
                "coracao_cm3": None,
                "pescoco": (False, u"pescoco: nao (dublado)")}

    class _Done(object):
        def __init__(self, uid):
            self.uid = uid

        def write_text(self, texto=u"", *a, **k):
            dones[self.uid] = json.loads(texto)
            return 0
    marc = {"has_marker": lambda *a, **k: False,
            "claim": lambda *a, **k: True,
            "unclaim": lambda *a, **k: None,
            "renovar": lambda *a, **k: None,
            "m_path": lambda pasta, uid, *a, **k: _Done(uid)}
    velho_cfg = dict(L._CFG)

    def _rodar_as_quatro(fn=None):
        _SaidaEspia.anotado.clear()
        pedidas.clear()
        dones.clear()
        corpo = {"series": [
            {"uid": uids["sem"], "pasta": os.path.join(estudo, "S2"),
             "modalidade": "CT", "pid": "F", "curto": "s", "date": "20260101"},
            {"uid": uids["fast"], "pasta": os.path.join(estudo, "S3"),
             "modalidade": "CT", "pid": "F", "curto": "f", "date": "20260101",
             "modo": "fast", "tasks": {"lung_nodules": 1},
             "comparacao": {"ts": 1, "nv": 1}},
            {"uid": uids["auto"], "pasta": os.path.join(estudo, "S4"),
             "modalidade": "CT", "pid": "F", "curto": "a", "date": "20260101",
             "modo": "auto", "comparacao": {"ts": 1}},
            {"uid": uids["perso"], "pasta": os.path.join(estudo, "S5"),
             "modalidade": "CT", "pid": "F", "curto": "p", "date": "20260101",
             "modo": "perso", "protocolos": ["torax_mama"],
             "tasks": {"abdominal_muscles": 0, "lung_nodules": 1,
                       "lung_vessels": 1},
             "comparacao": {"ts": 1, "nv": 1, "mse": 1},
             "oar_fora": ["heart"]}]}
        res = {}
        for s in L._com_escolhas_da_tela(corpo):
            _SaidaEspia.atual["uid"] = s["uid"]
            res[s["uid"]] = (fn or L._uma_serie)(
                s, False, ["total_v3"], "cpu", None, 60, 60, None, marc,
                "BATERIA", 3600, 0.0)
        return res
    try:
        _dublar_o_motor(E, dublados, _ts, _regioes)
        L._CFG.clear()
        res = _rodar_as_quatro()
        checar(u"as quatro series foram ate o fim sem erro",
               all(not r.get("erro") for r in res.values()),
               u" | ".join(str(r.get("erro"))[:80] for r in res.values()))
        import radai_tasks as _rtk
        _fam = _rtk.familia_da_task

        def _sem_base(lst):
            return [t for t in lst if _fam(t) != "total"]

        def _base_primeiro(lst):
            return bool(lst) and _fam(lst[0]) == "total"
        ped = dict((c, pedidas.get(u, [])) for c, u in uids.items())
        _tor = ["trunk_cavities", "breasts", "pleural_pericard_effusion"]
        checar(u"a serie SEM modo e AUTO: a base e o que a anatomia pede",
               _base_primeiro(ped["sem"]) and _sem_base(ped["sem"]) == _tor,
               str(ped["sem"]))
        checar(u"  e o AUTO declarado pede o mesmo",
               _sem_base(ped["auto"]) == _tor, str(ped["auto"]))
        checar(u"o FAST pede as tres do torax (a cavidade, a glandula e o "
               u"derrame)", _sem_base(ped["fast"]) == _tor,
               str(ped["fast"]))
        checar(u"  e a chave de achado mandada numa serie FAST nao liga nada",
               "lung_nodules" not in ped["fast"], str(ped["fast"]))
        checar(u"o PERSONALIZADO pede o protocolo e as chaves, e a chave "
               u"desligada VENCE o protocolo",
               set(_sem_base(ped["perso"])) == {"trunk_cavities", "breasts",
                                                "lung_nodules",
                                                "lung_vessels",
                                                "pleural_pericard_effusion"},
               str(ped["perso"]))
        ach = set(getattr(E, "TASKS_DE_ACHADO", ()) or ())
        checar(u"REGRA A: FAST e AUTO nao pedem achado",
               not (set(ped["sem"] + ped["fast"] + ped["auto"]) & ach))
        checar(u"  e o achado LIGADO pela chave chega ao motor (regra B)",
               "lung_nodules" in ped["perso"])
        an = dict((c, _SaidaEspia.anotado.get(u) or {})
                  for c, u in uids.items())
        _modos = dict((c, (an[c].get("full_e_oar") or {}).get("modo"))
                      for c in uids)
        checar(u"o MODO de cada serie chega a porta do entregue",
               _modos == {"sem": "auto", "fast": "fast", "auto": "auto",
                          "perso": "perso"}, str(_modos))
        checar(u"  e o «x» do OAR so no PERSONALIZADO",
               (an["perso"].get("full_e_oar") or {}).get("oar_fora")
               == ["heart"] and not (an["auto"].get("full_e_oar") or {})
               .get("oar_fora"),
               str((an["perso"].get("full_e_oar") or {}).get("oar_fora")))
        _lado = dict((c, sorted(set(an[c].get("chamadas") or [])
                                - {"full_e_oar", "pelvicos"}))
                     for c in uids)
        checar(u"o FAST so grava o OAR_Fast: nada ao lado (sem TS cru, sem "
               u"plugins, sem comparacao)", _lado["fast"] == [],
               str(_lado["fast"]))
        checar(u"o AUTO grava so o FULL e o OAR: sem TS cru, mesmo com a "
               u"chave mandada", _lado["sem"] == [] and _lado["auto"] == [],
               u"%s | %s" % (_lado["sem"], _lado["auto"]))
        checar(u"o PERSONALIZADO grava o TS cru (a chave), os plugins e a "
               u"comparacao ligada",
               {"totalsegmentator_cru", "plugins", "nv", "moose",
                "rodou_nv", "rodou_mse"} <= set(_lado["perso"])
               and "rodou_cads" not in _lado["perso"], str(_lado["perso"]))
        _dm = dict((c, (dones.get(u) or {}).get("modo")) for c, u in
                   uids.items())
        checar(u"o `done` grava o modo de cada serie",
               _dm == {"sem": "auto", "fast": "fast", "auto": "auto",
                       "perso": "perso"}, str(_dm))
        checar(u"  e o `rs` do FAST e o arquivo que foi ao TPS "
               u"(`RS_RadAI_FAST_*`)",
               str((dones.get(uids["fast"]) or {}).get("rs", u""))
               .startswith(u"RS_RadAI_FAST_")
               and res[uids["fast"]].get("rs", u"").startswith(
                   u"RS_RadAI_FAST_"),
               str((dones.get(uids["fast"]) or {}).get("rs")))

        src = inspect.getsource(L._uma_serie)

        def _com(de, para, nome):
            ns = dict(vars(L))
            exec(compile(src.replace(de, para), nome, "exec"), ns)
            return de in src, ns["_uma_serie"]
        achou, f1 = _com(u"modo=_modo_da_saida,", u'modo="auto",',
                         "<isca-modo>")
        _rodar_as_quatro(f1)
        m1 = ((_SaidaEspia.anotado.get(uids["fast"]) or {}).get(
            "full_e_oar") or {}).get("modo")
        checar(u"ISCA: sem o modo na porta do entregue, o FAST grava o FULL "
               u"(a checagem sabe reprovar)", achou and m1 == "auto", str(m1))
        achou, f2 = _com(u"        if _origem == _md.MODO_PERSO:\n"
                         u"            if ts_cru_pedido(s):",
                         u"        if True:\n            if True:",
                         "<isca-lado>")
        _rodar_as_quatro(f2)
        l2 = set((_SaidaEspia.anotado.get(uids["fast"]) or {})
                 .get("chamadas") or [])
        checar(u"ISCA: com a gravacao ao lado fora do PERSONALIZADO, o FAST "
               u"grava o TS cru e os plugins (a checagem sabe reprovar)",
               achou and {"totalsegmentator_cru", "plugins"} <= l2,
               str(sorted(l2)))
        achou, f3 = _com(u"                     modo=(_origem if _origem in "
                         u"_md.MODOS_DA_SERIE\n", u"                     "
                         u"modo=(None if _origem in _md.MODOS_DA_SERIE\n",
                         "<isca-done>")
        _rodar_as_quatro(f3)
        checar(u"ISCA: sem o modo no `done`, a chave some (a checagem sabe "
               u"reprovar)", achou and "modo" not in (
                   dones.get(uids["fast"]) or {}), str(achou))
    finally:
        for obj, nome, val in reversed(dublados):
            setattr(obj, nome, val)
        L._CFG.clear()
        L._CFG.update(velho_cfg)
        shutil.rmtree(base, ignore_errors=True)


def teste_os_niveis_cervicais_saem_pelo_rodar_agora():
    secao(u"os niveis cervicais saem pelo «Rodar agora»")
    import inspect
    import engine as E

    base = tempfile.mkdtemp(prefix="radai_t_hnl_")
    estudo = os.path.join(base, "PAC", "ESTUDO")
    uids = {}
    casos = (("auto_pes", 2), ("auto_sem", 3), ("perso_chave", 4),
             ("perso_prot", 5), ("perso_prot_off", 6), ("fast_pes", 7),
             ("rm_pes", 8))
    for cod, n in casos:
        uids[cod] = _serie(os.path.join(estudo, "S%d" % n), n, 8, 3.0,
                           "B30f", "PESCOCO %s" % cod,
                           modalidade=("MR" if cod == "rm_pes" else "CT"))
    com_pescoco = set([uids["auto_pes"], uids["fast_pes"], uids["rm_pes"],
                       uids["perso_prot"], uids["perso_chave"],
                       uids["perso_prot_off"]])
    ts_kw, niveis = {}, {}
    dublados = []

    def _ts(ref, t, **k):
        ts_kw.setdefault(_SaidaEspia.atual["uid"], []).append(
            k.get("recorte_no_corpo", u"AUSENTE"))
        if k.get("cruas") is not None:
            k["cruas"][t] = {"skull": 1}
        return {"liver_%s" % t: 1}

    def _regioes(masks, grade, cruas=None, motor=None):
        tem = _SaidaEspia.atual["uid"] in com_pescoco
        return {"regioes": (("cabeca_pescoco",) if tem else ("torax",)),
                "laudo": [u"dublada"], "coracao_cm3": None,
                "pescoco": (tem, u"pescoco: %s (dublado)"
                            % (u"sim" if tem else u"nao"))}

    def _niveis(ref, cruas, device="cpu", log=None):
        niveis.setdefault(_SaidaEspia.atual["uid"], []).append(
            sorted(cruas or {}))
        return {"LNL01": 1, "LNL_Union": 1}

    class _Nada(object):
        def write_text(self, *a, **k):
            return 0
    marc = {"has_marker": lambda *a, **k: False,
            "claim": lambda *a, **k: True,
            "unclaim": lambda *a, **k: None,
            "renovar": lambda *a, **k: None,
            "m_path": lambda *a, **k: _Nada()}
    import radai_output as RO
    velho_cfg = dict(L._CFG)

    def _rodar(fn=None):
        _SaidaEspia.anotado.clear()
        niveis.clear()
        ts_kw.clear()
        corpo = {"series": [
            {"uid": uids["auto_pes"], "modo": "auto"},
            {"uid": uids["auto_sem"], "modo": "auto"},
            {"uid": uids["perso_chave"], "modo": "perso",
             "tasks": {L.CHAVE_DOS_NIVEIS: 1}},
            {"uid": uids["perso_prot"], "modo": "perso",
             "protocolos": ["cabeca_pescoco"]},
            {"uid": uids["perso_prot_off"], "modo": "perso",
             "protocolos": ["cabeca_pescoco"],
             "tasks": {L.CHAVE_DOS_NIVEIS: 0}},
            {"uid": uids["fast_pes"], "modo": "fast"},
            {"uid": uids["rm_pes"], "modo": "auto", "modalidade": "MR"}]}
        for i, (cod, n) in enumerate(casos):
            corpo["series"][i].update({
                "pasta": os.path.join(estudo, "S%d" % n), "pid": "F",
                "curto": cod[:6]})
            corpo["series"][i].setdefault("modalidade", "CT")
        res = {}
        for s in L._com_escolhas_da_tela(corpo):
            _SaidaEspia.atual["uid"] = s["uid"]
            res[s["uid"]] = (fn or L._uma_serie)(
                s, False, ["total_v3"], "cpu", None, 60, 60, None, marc,
                "BATERIA", 3600, 0.0)
        return res
    try:
        _dublar_o_motor(E, dublados, _ts, _regioes)
        dublados.append((RO, "niveis_cervicais_da_serie",
                         RO.niveis_cervicais_da_serie))
        RO.niveis_cervicais_da_serie = _niveis
        L._CFG.clear()
        L._CFG.update({"incluir_hnlnl": 1, "recorte_no_corpo": 0})
        res = _rodar()
        checar(u"as sete series foram ate o fim sem erro",
               all(not r.get("erro") for r in res.values()),
               u" | ".join(str(r.get("erro"))[:80] for r in res.values()))
        import radai_tasks as _rtk

        def _com_a_base(chamadas):
            return (len(chamadas or ()) == 1 and any(
                _rtk.familia_da_task(t) == "total" for t in chamadas[0]))
        rodou = dict((c, bool(niveis.get(u))) for c, u in uids.items())
        checar(u"AUTO com o pescoco: os niveis rodam, com as cruas da serie",
               _com_a_base(niveis.get(uids["auto_pes"])),
               str(niveis.get(uids["auto_pes"])))
        checar(u"AUTO sem o pescoco: nao rodam (com a chave velha ligada)",
               not rodou["auto_sem"])
        checar(u"PERSONALIZADO com a chave dos niveis: rodam",
               rodou["perso_chave"])
        checar(u"  e com o protocolo Cabeca e Pescoco avancado: rodam",
               rodou["perso_prot"])
        checar(u"  e com o protocolo e a chave em 0: NAO rodam (a chave vence)",
               not rodou["perso_prot_off"])
        checar(u"FAST nunca roda os niveis (sem FULL, nao teriam onde entrar)",
               not rodou["fast_pes"])
        checar(u"RM nunca (o modelo dos niveis e de TC)", not rodou["rm_pes"])
        an = dict((c, _SaidaEspia.anotado.get(u) or {})
                  for c, u in uids.items())

        def _cerv(c):
            return (an[c].get("full_e_oar") or {}).get("cervicais")
        checar(u"os niveis entram no FULL (`full_e_oar(cervicais=...)`) no "
               u"AUTO e no PERSONALIZADO",
               bool(_cerv("auto_pes")) and bool(_cerv("perso_chave"))
               and not _cerv("auto_sem"))
        checar(u"  e o arquivo proprio (`HNL_`) so no PERSONALIZADO — no AUTO "
               u"eles vao so ao FULL (spec 1.1)",
               "niveis_cervicais" in (an["perso_chave"].get("chamadas") or ())
               and "niveis_cervicais" not in (an["auto_pes"].get("chamadas")
                                              or ()))
        todas = [v for vs in ts_kw.values() for v in vs]
        checar(u"com RECORTE_NO_CORPO=0 na estacao, TODA task recebe "
               u"recorte_no_corpo=False", todas and all(v is False
                                                        for v in todas),
               str(todas))
        m, o = L.motores_da_serie({"modo": "auto"})
        checar(u"no plano, o AUTO nao liga os niveis (o pescoco decide depois)",
               m.get("hnlnl") is False and o == "auto", str((m, o)))
        L._CFG.pop("recorte_no_corpo", None)
        checar(u"sem RECORTE_NO_CORPO injetado, o lote passa None (o motor "
               u"decide)", L.recorte_no_corpo_da_estacao() is None)
        L._CFG["recorte_no_corpo"] = True
        checar(u"  e com 1 injetado, passa True",
               L.recorte_no_corpo_da_estacao() is True)
        L._CFG["recorte_no_corpo"] = 0
        src = inspect.getsource(L._uma_serie)
        alvo = u'_mot["hnlnl"] = bool(_niveis["rodam"])'
        ns = dict(vars(L))
        exec(compile(src.replace(alvo, u'_mot["hnlnl"] = True'),
                     "<isca-pescoco>", "exec"), ns)
        _rodar(ns["_uma_serie"])
        checar(u"ISCA: sem o pescoco decidindo, o AUTO sem pescoco roda os "
               u"niveis (a checagem sabe reprovar)",
               alvo in src and bool(niveis.get(uids["auto_sem"])))

        niv = L._item_dos_niveis("CT") or {}
        cx = niv.get("caixa") or u""
        checar(u"a tela oferece os niveis na coluna das tasks",
               niv.get("task") == L.CHAVE_DOS_NIVEIS)
        checar(u"  e o texto da caixa diz: so com a cabeca no campo, os nomes "
               u"de Gregoire e, no OAR, so a uniao e as parotidas do VIII",
               u"cabeça no campo" in cx and u"Grégoire" in cx
               and u"união" in cx and u"parótidas do nível VIII" in cx
               and u"LNL01" not in cx, cx)

        import ast as _ast
        _arv = _ast.parse(io.open(_componentes.fonte("app/radai_modes.py"),
                                  encoding="utf-8").read())
        _lits = set(n.value for n in _ast.walk(_arv)
                    if isinstance(n, _ast.Constant) and isinstance(n.value, str))
        try:
            _alimentam = tuple(E.motores_que_alimentam())
        except Exception:
            _alimentam = None
        _aj = dict((c["cod"], c.get("ajuda") or u"")
                   for c in L.comparacao_da_tela("CT") if c["cod"] != "ts")
        _aj["hnlnl"] = niv.get("ajuda") or u""
        checar(u"a ajuda de cada motor e feita de linhas que SAO literais do "
               u"fonte (o tradutor casa cada `<p>`)",
               _aj and all(l in _lits for a in _aj.values()
                           for l in a.split(u"\n")),
               str([l[:50] for a in _aj.values() for l in a.split(u"\n")
                    if l not in _lits]))
        if _alimentam is not None:
            checar(u"  e a frase derivada e uma linha PROPRIA, a segunda",
                   all(len(a.split(u"\n")) == 2
                       and u"conjunto final" in a.split(u"\n")[1]
                       for c, a in _aj.items() if c != "hnlnl"),
                   str([a.split(u"\n")[-1][:40] for a in _aj.values()]))
        checar(u"nenhuma ajuda de motor tem crase (a tela a mostraria)",
               all(u"`" not in a for a in _aj.values()),
               str([c for c, a in _aj.items() if u"`" in a]))
        _ui = io.open(_componentes.fonte("app/radai_ui.py"), encoding="utf-8").read()
        checar(u"  e o painel faz um `<p>` por linha do corpo",
               u"String(o.corpo" in _ui
               and u".split(String.fromCharCode(10))" in _ui)
    finally:
        for obj, nome, val in reversed(dublados):
            setattr(obj, nome, val)
        L._CFG.clear()
        L._CFG.update(velho_cfg)
        shutil.rmtree(base, ignore_errors=True)


def teste_o_explorador_do_passo_1():
    secao(u"o explorador do passo 1")
    import time as _t
    base = tempfile.mkdtemp(prefix="radai_t_expl_")
    try:
        for nome, idade_h in ((u"BETA", 50), (u"alfa", 1), (u"Gama", 20)):
            p = os.path.join(base, nome)
            os.makedirs(p)
            ts = _t.time() - idade_h * 3600
            os.utime(p, (ts, ts))
        io.open(os.path.join(base, "IM00001"), "wb").write(b"DICM")
        io.open(os.path.join(base, "EXAME.zip"), "wb").write(b"PK")
        d = L.listar_pastas_do_explorador(base, ordem="nome", sentido="asc")
        nomes = [p["nome"] for p in d["pastas"]]
        checar(u"so pastas -- nenhum arquivo na lista", nomes and all(
            n in (u"alfa", u"BETA", u"Gama") for n in nomes), str(nomes))
        checar(u"ordem por NOME, sem diferenca de caixa",
               nomes == [u"alfa", u"BETA", u"Gama"], str(nomes))
        checar(u"  e a descendente inverte",
               [p["nome"] for p in L.listar_pastas_do_explorador(
                   base, ordem="nome", sentido="desc")["pastas"]]
               == [u"Gama", u"BETA", u"alfa"])
        dd = L.listar_pastas_do_explorador(base, ordem="data", sentido="desc")
        checar(u"ordem por DATA: a mais recente primeiro",
               [p["nome"] for p in dd["pastas"]] == [u"alfa", u"Gama", u"BETA"],
               str([p["nome"] for p in dd["pastas"]]))
        checar(u"  e cada pasta traz a data de modificacao",
               all(re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$", p["data"])
                   for p in dd["pastas"]), str([p["data"] for p in dd["pastas"]]))
        checar(u"a busca filtra ANTES do teto, sem acento e sem caixa",
               [p["nome"] for p in L.listar_pastas_do_explorador(
                   base, busca=u"ÁLF")["pastas"]] == [u"alfa"])
        checar(u"o pai e dito pelo servidor",
               os.path.normcase(L.listar_pastas_do_explorador(
                   os.path.join(base, u"alfa"))["pai"])
               == os.path.normcase(os.path.abspath(base)))
        ruim = L.listar_pastas_do_explorador(os.path.join(base, u"nao_existe"))
        checar(u"caminho que nao existe diz o motivo", bool(ruim["erro"])
               and not ruim["pastas"], ruim["erro"])
        checar(u"o motivo do caminho ruim e uma frase sem valor dentro",
               not re.search(r"\d", ruim["erro"] or u"x"), ruim["erro"])
        cheia = L.listar_pastas_do_explorador(base, teto=2)
        checar(u"passar do teto manda os NUMEROS separados da frase",
               cheia.get("mostrando") == 2 and cheia.get("total") == 3
               and len(cheia["pastas"]) == 2,
               u"mostrando=%r total=%r" % (cheia.get("mostrando"),
                                           cheia.get("total")))
        checar(u"  e a dica e uma frase inteira, e o teto nao e erro",
               cheia.get("dica") and not re.search(r"\d", cheia["dica"])
               and not cheia.get("erro"),
               u"dica=%r erro=%r" % (cheia.get("dica"), cheia.get("erro")))

        import threading as _th
        guardado = (L._letras_montadas, L._UNIDADES["quando"],
                    list(L._UNIDADES["lista"]))
        _exists = os.path.exists
        solta = _th.Event()

        def _lento(r):
            if str(r).upper().startswith(u"Q:"):
                solta.wait(5)
                return True
            return _exists(r)
        try:
            L._letras_montadas = lambda: [u"C", u"Q"]
            L._UNIDADES["quando"] = 0.0
            L._UNIDADES["lista"] = []
            os.path.exists = _lento
            t0 = _t.time()
            un = L.unidades_do_explorador(teto_s=1.0, validade_s=0)
            dt = _t.time() - t0
        finally:
            os.path.exists = _exists
            solta.set()
            L._letras_montadas = guardado[0]
            L._UNIDADES["quando"], L._UNIDADES["lista"] = guardado[1], guardado[2]
        if os.name == "nt":
            checar(u"a unidade lenta nao segura a lista (prazo de 1 s)",
                   dt < 2.5, u"%.1f s" % dt)
            q = [u2 for u2 in un if u2["raiz"].upper().startswith(u"Q:")]
            checar(u"  e ela aparece como «nao respondeu», e nao some",
                   bool(q) and q[0]["ok"] is None, str(un))
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from fastapi import FastAPI
                from fastapi.testclient import TestClient
            app = FastAPI()
            L.montar(app, {"tasks": ["total"], "device": "cpu"})
            cli = TestClient(app)
            checar(u"`GET /api/lote/pastas` nao existe -- caminho nao vai em URL",
                   cli.get("/api/lote/pastas?caminho=" + base).status_code == 405)
            r = cli.post("/api/lote/pastas", json={"caminho": base,
                                                   "ordem": "data",
                                                   "sentido": "desc"})
            checar(u"`POST` responde com a mesma lista",
                   [p["nome"] for p in (r.json() or {}).get("pastas") or ()]
                   == [u"alfa", u"Gama", u"BETA"], r.text[:120])
        except ImportError as e:
            checar(u"a rota responde (fastapi ausente)", True, str(e))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_o_otimizar_saiu_do_lote():
    secao(u"o lote nao sugere nem aplica mais o Otimizar")
    for nome in ("sugestao_de_otimizacao", "otimizar_estacao",
                 "ocupantes_da_placa"):
        checar(u"`%s` saiu" % nome, not hasattr(L, nome))
    try:
        from fastapi import FastAPI
        app = FastAPI()
        L.montar(app, {"tasks": ["total"], "device": "cpu"})
        rotas = set(getattr(r, "path", u"") for r in app.routes)
        checar(u"as rotas /api/lote/otimizacao e /api/lote/otimizar sairam",
               not ({"/api/lote/otimizacao", "/api/lote/otimizar"} & rotas)
               and "/api/pipeline/iniciar" in rotas, len(rotas))
    except ImportError as e:
        checar(u"as rotas (fastapi ausente)", True, str(e))
    js = L.PAGINA
    checar(u"a folha do turno nao manda mais a pausa de servicos",
           u"pausar_servicos" not in js and u"ov_pausar" not in js)


def teste_o_andamento_vai_para_o_card_que_roda():
    secao(u"o andamento no card que roda")
    import radai_queue_state as F
    import radai_queue as Q
    guard = dict(L._JOB)
    try:
        with L._TRAVA:
            L._JOB.update({"rodando": True, "etapa": "segmentando: total_v3",
                           "parte": "", "serie_desde": 0.0})
            import time as _t
            L._JOB["serie_desde"] = _t.time() - 125
        L._sondar_parte(u"   TS total_v3 rodando... 600s (still working)")
        checar(u"linha sem parte nao inventa parte", L.andamento()["parte"] == u"")
        L._sondar_parte(u"   Predicting part 2 of 5")
        checar(u"a sonda le «part 2 of 5»", L.andamento()["parte"] == u"2/5",
               L.andamento()["parte"])
        L._sondar_parte(u"parte 3/5 do total_v3")
        checar(u"  e «parte 3/5»", L.andamento()["parte"] == u"3/5")
        a = L.andamento()
        checar(u"o tempo e o da SERIE, e anda",
               a["segundos"] is not None and 120 <= a["segundos"] <= 200,
               str(a["segundos"]))
        L._passo("segmentando 1/2: head_glands_cavities")
        checar(u"trocar de task zera a parte (a de antes nao vale para esta)",
               L.andamento()["parte"] == u"")
        cards = [Q.novo_card(Q.SERIE, rotulo=u"PAC", uid=u"1.2.3.4.5.6.7.8.9"),
                 Q.novo_card(Q.SERIE, rotulo=u"OUTRA", uid=u"9.9")]
        cards[0]["estado"] = Q.RODANDO
        fora = F.com_andamento(F.para_tela(cards), L.andamento())
        checar(u"so o card que RODA recebe o andamento",
               "andamento" in fora[0] and "andamento" not in fora[1])
        txt = repr(fora[0]["andamento"])
        checar(u"  e ele nao carrega caminho nem UID",
               u"1.2.3.4.5.6.7.8.9" not in txt and u"pasta" not in txt, txt)
        import contextlib
        import io as _io

        class _Quebrada(object):
            def search(self, *_a):
                raise TypeError(u"sonda dublada")
        g_parte = L._PARTE
        del L._SONDA_AVISOU[:]
        buf = _io.StringIO()
        levantou = False
        try:
            L._PARTE = _Quebrada()
            with contextlib.redirect_stdout(buf):
                try:
                    L._sondar_parte(u"parte 1/5")
                    L._sondar_parte(u"parte 2/5")
                except Exception:
                    levantou = True
        finally:
            L._PARTE = g_parte
            del L._SONDA_AVISOU[:]
        checar(u"a sonda que falha nao levanta (a serie nao cai por ela)",
               not levantou)
        checar(u"  e diz na tela preta, uma vez so",
               buf.getvalue().count(u"[lote]") == 1
               and u"TypeError" in buf.getvalue(), buf.getvalue()[:160])
    finally:
        with L._TRAVA:
            L._JOB.clear()
            L._JOB.update(guard)


def teste_a_conferencia_soma_os_modos_das_series():
    secao(u"a conferencia soma as escolhas das series")
    import radai_queue_state as F
    F.limpar()
    velho = dict(L._CFG)
    try:
        L._CFG.clear()
        F.pedir(L._com_escolhas_da_tela({"series": [
            {"uid": "A1", "pasta": "pa", "modalidade": "CT"},
            {"uid": "B2", "pasta": "pb", "modalidade": "CT", "modo": "perso",
             "protocolos": ["torax_mama"],
             "tasks": {"lung_nodules": 1, L.CHAVE_DOS_NIVEIS: 1},
             "comparacao": {"ts": 1, "nv": 1, "cads": 1, "mse": 1}}]}))
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        app = FastAPI()
        L.montar(app, {"tasks": ["total_v3"], "device": "cpu"})
        _pedido = {}
        import radai_review as _rvm
        _montar = _rvm.montar
        try:
            _rvm.montar = lambda *a, **k: (_pedido.update(k) or _montar(*a, **k))
            rv = (TestClient(app).get("/api/pipeline/revisao").json()
                  or {}).get("revisao") or {}
        finally:
            _rvm.montar = _montar
        so_base = L.tasks_previstas({"modo": "auto"})
        checar(u"a conferencia anuncia o que a serie PERSONALIZADA roda, e nao "
               u"so a base",
               len(rv.get("tasks") or ()) > len(so_base)
               and "lung_nodules" in (rv.get("tasks") or ())
               and "breasts" in (rv.get("tasks") or ()),
               u"anunciou %s, a base sozinha e %s"
               % (rv.get("tasks"), so_base))
        sai = dict((c["cod"], c["sai"]) for c in rv.get("conjuntos") or ())
        checar(u"  e a comparacao LIGADA aparece como «sai»",
               sai.get("nv") and sai.get("cads") and sai.get("mse"), str(sai))
        checar(u"  e o TS cru pedido pela chave tambem",
               sai.get("ts") is True and _pedido.get("incluir_ts") is True,
               str((sai.get("ts"), _pedido.get("incluir_ts"))))
        _pl = dict((c["cod"], c) for c in rv.get("conjuntos") or ()
                   if c.get("plugin"))
        checar(u"  e o plugin da chave de achado aparece como arquivo que sai, "
               u"com o selo", "nod" in _pl and _pl["nod"].get("sai")
               and _pl["nod"].get("achado"), str(sorted(_pl)))
        checar(u"  e a abdominal_muscles (que alimenta o FULL inteira) nao "
               u"promete arquivo proprio", "abm" not in _pl, str(sorted(_pl)))
        checar(u"  a rota soma os niveis das series (incluir_hnlnl=True)",
               _pedido.get("incluir_hnlnl") is True,
               str(_pedido.get("incluir_hnlnl")))
        hn = [c for c in rv.get("conjuntos") or () if c["cod"] == "hnl"]
        checar(u"  e a revisao diz que os niveis SAEM, com o portao da cabeca "
               u"no campo", hn and hn[0]["sai"]
               and u"cabeça no campo" in hn[0]["porque"], str(hn))
        ests = dict((m["cod"], m["n"]) for m in rv.get("estudos") or ())
        checar(u"  e diz quantas series em cada modo, e os protocolos do "
               u"PERSONALIZADO",
               ests == {"auto": 1, "perso": 1, "perso:torax_mama": 1},
               str(ests))
        _rot = dict((m["cod"], m["rotulo"]) for m in rv.get("estudos") or ())
        checar(u"  com o rotulo do modo e o do protocolo (o da tela)",
               _rot.get("perso") == u"PERSONALIZADO"
               and _rot.get("perso:torax_mama") == u"Tórax / Mama", str(_rot))
        F.limpar()
        F.pedir(L._com_escolhas_da_tela({"series": [
            {"uid": "A1", "pasta": "pa", "modalidade": "CT"}]}))
        rv = (TestClient(app).get("/api/pipeline/revisao").json() or {}).get(
            "revisao") or {}
        cj = dict((c["cod"], c) for c in rv.get("conjuntos") or ())
        checar(u"so AUTO: o NV nao sai, e o motivo diz que e pedido do "
               u"PERSONALIZADO", not cj["nv"]["sai"]
               and u"PERSONALIZADO" in cj["nv"]["porque"]
               and u"Comparação de modelos" in cj["nv"]["porque"],
               str(cj.get("nv")))
        checar(u"  e o TS cru NAO sai por omissao (spec 1.1), com o motivo",
               not cj["ts"]["sai"] and u"TS cru" in cj["ts"]["porque"],
               str(cj.get("ts")))
        checar(u"  e o FULL e o OAR saem, e o OAR_Fast nao aparece",
               cj["oar"]["sai"] and cj["full"]["sai"] and "fast" not in cj)
        F.limpar()
        F.pedir(L._com_escolhas_da_tela({"series": [
            {"uid": "F1", "pasta": "pf", "modalidade": "CT", "modo": "fast"}]}))
        rv = (TestClient(app).get("/api/pipeline/revisao").json() or {}).get(
            "revisao") or {}
        cj = dict((c["cod"], c) for c in rv.get("conjuntos") or ())
        checar(u"so FAST: o RadAI_STUDY_Fast sai, e e o entregue",
               (cj.get("fast") or {}).get("sai") is True
               and (cj.get("fast") or {}).get("entregue") is True,
               str(cj.get("fast")))
        checar(u"  e o FULL e o OAR NAO saem, com o motivo",
               not cj["oar"]["sai"] and not cj["full"]["sai"]
               and u"FAST" in cj["full"]["porque"], str(cj.get("full")))
        checar(u"  e a conferencia nao diz mais «nao sai por esta porta»",
               all(u"por esta porta" not in (c.get("porque") or u"")
                   for c in rv.get("conjuntos") or ()))
        _cp = _rvm._conjuntos_previstos(incluir_ts=None, por_serie=True,
                                        modos={"auto": 1})
        checar(u"ISCA: sem `incluir_ts`, a conferencia promete o TS cru (a "
               u"checagem sabe reprovar)",
               dict((c["cod"], c["sai"]) for c in _cp).get("ts") is True)
    except ImportError as e:
        checar(u"a rota responde (fastapi ausente)", True, str(e))
    finally:
        F.limpar()
        L._CFG.clear()
        L._CFG.update(velho)


def teste_a_regua_de_cpu_tem_uma_fonte_so():
    secao(u"a regua de CPU tem uma fonte so")
    import ast
    import radai_arranque as RA
    import radai_review as RV
    checar(u"a conferencia usa a regua do `radai_arranque` (o mesmo objeto)",
           RV.MIN_POR_MVOXEL_CPU is RA.MIN_POR_MVOXEL_CPU,
           u"%r vs %r" % (RV.MIN_POR_MVOXEL_CPU, RA.MIN_POR_MVOXEL_CPU))
    literais = []
    for nome in _componentes.nomes("app"):
        if not nome.endswith(".py") or nome == "radai_arranque.py":
            continue
        try:
            arv = ast.parse(io.open(_componentes.fonte("app/" + nome),
                                    encoding="utf-8").read())
        except Exception:
            continue
        for n in ast.walk(arv):
            if (isinstance(n, ast.Assign)
                    and any(getattr(t, "id", "") == "MIN_POR_MVOXEL_CPU"
                            for t in n.targets)
                    and isinstance(n.value, ast.Constant)
                    and isinstance(n.value.value, (int, float))):
                literais.append(u"%s:%d" % (nome, n.lineno))
    checar(u"  e nenhum outro arquivo de app/ escreve o numero",
           not literais, str(literais))


def teste_a_ficha_diz_o_recorte_da_estacao():
    secao(u"a ficha diz o recorte no corpo da estacao")
    import radai_tasks as RT
    velho_cfg = dict(L._CFG)
    velho_peso = RT.pesos_do_recorte_no_corpo

    def _campo(o):
        t = o.get("base_item") or {}
        if t.get("task") == o.get("base"):
            for f in t.get("ficha") or ():
                if f.get("rot") == u"campo de trabalho":
                    return f.get("val")
        return None
    try:
        RT.pesos_do_recorte_no_corpo = lambda *a, **k: (True, u"dublado")
        L._CFG.clear()
        L._CFG.update(velho_cfg)
        L._CFG["recorte_no_corpo"] = True
        v1 = _campo(L.opcoes_da_tela("CT"))
        L._CFG["recorte_no_corpo"] = False
        v0 = _campo(L.opcoes_da_tela("CT"))
        L._CFG.pop("recorte_no_corpo", None)
        vn = _campo(L.opcoes_da_tela("CT"))
    finally:
        RT.pesos_do_recorte_no_corpo = velho_peso
        L._CFG.clear()
        L._CFG.update(velho_cfg)
    checar(u"com a chave ligada (e o peso), a ficha da base diz «so o corpo»",
           v1 == u"só o corpo, sem o ar em volta", v1)
    checar(u"  com RECORTE_NO_CORPO=0, «a serie inteira» — e nao «so o corpo»",
           v0 == u"a série inteira", v0)
    checar(u"  sem a chave injetada, o padrao do MOTOR decide (e nao a frase "
           u"condicional)", vn == u"só o corpo, sem o ar em volta", vn)


def teste_a_conferencia_diz_o_que_nao_calculou():
    secao(u"a conferencia diz o que nao calculou")
    import radai_modes as md
    import radai_queue_state as F
    F.limpar()
    velho = dict(L._CFG)
    guardadas = (L.tasks_previstas, L.motores_da_serie)
    try:
        L._CFG.clear()
        L._CFG.update({"incluir_nv": 0, "incluir_cads": 0, "incluir_moose": 0})
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        app = FastAPI()
        L.montar(app, {"tasks": ["lista_do_config_isca"], "device": "cpu",
                       "incluir_nv": 0, "incluir_cads": 0, "incluir_moose": 0})
        cli = TestClient(app)
        F.pedir([{"uid": "1.2.3.40001111", "pasta": "pa", "modalidade": "CT",
                  "estudos": []},
                 {"uid": "1.2.3.40002222", "pasta": "pb", "modalidade": "CT",
                  "estudos": ["torax"],
                  "tasks_extra": ["trunk_cavities"]}])

        def _tasks_falha_na_b(s, lista):
            if str(s.get("uid") or "").endswith("2222"):
                raise ValueError(u"trava da regra A recusou (dublado)")
            return guardadas[0](s, lista)

        def _motores_falha_na_a(s, *a, **k):
            if str(s.get("uid") or "").endswith("1111"):
                raise KeyError(u"motor dublado")
            return guardadas[1](s, *a, **k)
        L.tasks_previstas = _tasks_falha_na_b
        L.motores_da_serie = _motores_falha_na_a
        rv = (cli.get("/api/pipeline/revisao").json() or {}).get("revisao") or {}
        pb = dict(((p.get("uid8"), p.get("o_que")), p.get("erro"))
                  for p in rv.get("problemas") or ())
        checar(u"a serie cuja conta de TASKS falhou aparece, com o motivo",
               u"ValueError" in (pb.get((u"40002222", u"tasks")) or u""),
               str(rv.get("problemas")))
        checar(u"  e a de MOTORES tambem, e cada uma na sua pergunta",
               u"KeyError" in (pb.get((u"40001111", u"motores")) or u""),
               str(rv.get("problemas")))
        checar(u"  e o problema so leva os 8 ultimos do UID",
               all(len(k[0]) <= 8 for k in pb), str(list(pb)))

        def _sempre(*a, **k):
            raise RuntimeError(u"catalogo quebrado (dublado)")
        L.tasks_previstas = _sempre
        rv = (cli.get("/api/pipeline/revisao").json() or {}).get("revisao") or {}
        checar(u"se nenhuma conta fecha, a conferencia NAO anuncia a lista do "
               u"config", u"lista_do_config_isca" not in (rv.get("tasks") or ()),
               str(rv.get("tasks")))
        try:
            import radai_tasks as _rt
            _padrao = set(_rt.PADRAO)
        except Exception:
            _padrao = set()
        checar(u"  nem o padrao de fabrica no lugar dela",
               not (set(rv.get("tasks") or ()) & _padrao),
               str(rv.get("tasks")))
        checar(u"  e diz por que, uma linha por serie",
               len([p for p in rv.get("problemas") or ()
                    if p.get("o_que") == u"tasks"]) == 2,
               str(rv.get("problemas")))
        L.tasks_previstas, L.motores_da_serie = guardadas
        rv = (cli.get("/api/pipeline/revisao").json() or {}).get("revisao") or {}
        checar(u"com as contas fechando, a lista de problemas vem vazia",
               rv.get("problemas") == [], str(rv.get("problemas")))

        import contextlib
        import io as _io
        import radai_review as _rv
        _guard_md = sys.modules.get("radai_modes")
        _rv._AVISADOS.discard("estudos")
        buf = _io.StringIO()
        try:
            sys.modules["radai_modes"] = None
            with contextlib.redirect_stdout(buf):
                m1 = _rv._estudos_da_fila({u"torax": 1})
                m2 = _rv._estudos_da_fila({u"torax": 1})
        finally:
            sys.modules["radai_modes"] = _guard_md
            _rv._AVISADOS.discard("estudos")
        checar(u"sem `radai_modes`, a linha dos estudos sai da conferencia",
               m1 == [] and m2 == [], str((m1, m2)))
        checar(u"  e a tela preta diz por que, uma vez so",
               buf.getvalue().count(u"[revisao]") == 1, buf.getvalue()[:160])
    except ImportError as e:
        checar(u"a rota responde (fastapi ausente)", True, str(e))
    finally:
        L.tasks_previstas, L.motores_da_serie = guardadas
        F.limpar()
        L._CFG.clear()
        L._CFG.update(velho)


def teste_serie_zipada_grava_em_caminho_absoluto():
    secao(u"serie zipada: o caminho de escrita")
    import radai_batch as B
    import tempfile as _tf
    import shutil as _sh

    d = _tf.mkdtemp(prefix="radai_zipabs_")
    try:
        p1, e1 = B.resolver_pasta({"zip": "C:/nao/existe.zip", "pasta": d})
        checar(u"pasta ja absoluta volta igual, sem extrair", p1 == d and not e1,
               "%r %r" % (p1, e1))
    finally:
        _sh.rmtree(d, ignore_errors=True)

    p2, e2 = B.resolver_pasta({"zip": "C:/nao/existe.zip",
                               "pasta": "DICOM/ST1/SE1"})
    checar(u"relativo vai para a extracao e o erro NOMEIA o arquivo",
           not p2 and "existe.zip" in (e2 or ""), (e2 or "")[:60])

    fonte = io.open(_componentes.fonte("app/radai_batch.py"),
                    encoding="utf-8").read()
    corpo = fonte[fonte.index("def _uma_serie("):]
    i_res = corpo.find('s["pasta"] = _real')
    i_claim = corpo.find('marcadores["claim"]')
    i_done = corpo.find('marcadores["has_marker"]')
    fonte = corpo
    checar(u"a resolucao acontece ANTES do `claim`",
           i_res > 0 and i_claim > 0 and i_res < i_claim,
           "resolve=%d claim=%d" % (i_res, i_claim))
    checar(u"e ANTES do `has_marker` do `done`",
           i_res > 0 and i_done > 0 and i_res < i_done,
           "resolve=%d done=%d" % (i_res, i_done))
    checar(u"e FALHA FECHADO se o caminho nao ficar absoluto",
           "os.path.isabs(_real)" in fonte and "nada " in fonte)


def teste_a_modalidade_e_o_registro_saem_da_serie():
    secao(u"a modalidade e o registro saem da serie")
    import radai_modes as md
    import radai_records as RG
    import engine as E
    import SimpleITK as sitk

    paciente = u"ISCA BELTRANO 12345"
    base = tempfile.mkdtemp(prefix="radai_t_modal_")
    uid_ct = _serie(os.path.join(base, paciente, "CT"), 2, 8, 3.0, "B30f", "TC")
    uid_mr = _serie(os.path.join(base, paciente, "MR"), 3, 8, 3.0, "", "RM T1",
                    modalidade="MR")
    oar, rts, casos, saidas = {}, {}, {}, {}
    torax_da_serie = {}
    chamadas = {}
    atual = {"uid": ""}
    guardado = {}

    def _dublar(obj, nome, novo):
        guardado[(id(obj), nome)] = (obj, nome, getattr(obj, nome))
        setattr(obj, nome, novo)

    def _ref():
        img = sitk.Image(8, 8, 8, sitk.sitkInt16)
        img.SetSpacing((0.7, 0.7, 3.0))
        return img

    def _para_oar(masks, **k):
        chamadas.setdefault("para_oar", ((masks,), dict(k)))
        oar[atual["uid"]] = k.get("modalidade", u"(nao passou)")
        return masks

    def _rtst(stage, masks, **kw):
        chamadas.setdefault("build_rtstruct", ((stage, masks), dict(kw)))
        rts[atual["uid"]] = kw.get("modalidade", u"(nao passou)")
        f = os.path.join(base, "rt_%s.dcm" % atual["uid"][-6:])
        io.open(f, "wb").write(b"RT")
        return f, {1: "Liver_ai"}

    def _curar(masks, cads, log=None):
        if log:
            log(u"placa sem memoria: refazendo a task inteira em CPU")
        return masks, {}

    class _Saida(object):
        def __init__(self, *a, **k):
            chamadas.setdefault("Saida", (a, dict(k)))
            saidas[atual["uid"]] = k.get("modalidade", u"(nao passou)")
            self._log = k.get("log")
            self.gravados = []
            self._a = a

        def full_e_oar(self, *a, **k):
            chamadas.setdefault("full_e_oar", ((self,) + tuple(a), dict(k)))
            torax_da_serie[atual["uid"]] = k.get("torax", u"(nao passou)")
            _rs_dublado(self, self._a[2], self._a[3])
            if self._log:
                self._log(u"placa sem memoria: refazendo a task inteira "
                          u"em CPU")
            return {"estruturas": ["Liver_ai"], "oar": "", "full": ""}

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
    import radai_output as RO
    reais = {"full_e_oar": RO.Saida.full_e_oar,
             "Saida": RO.Saida, "registrar_serie": RG.registrar_serie}
    velho_cfg = dict(L._CFG)
    try:
        _dublar(E, "copy_sorted", lambda arqs, stage: None)
        _dublar(E, "load_sitk", lambda stage: _ref())
        _dublar(E, "_resolve_device", lambda d: "cpu")

        def _ts(ref, t, **k):
            e_rm = t.endswith("_mr")
            E._anotar_no_job(
                k.get("jid"), t,
                plano={"modo": "gpu", "motivo": "placa com folga"},
                recorte={"estado": u"nao se aplica" if e_rm else u"ligado",
                         "motivo": (u"a biblioteca ignora --body_seg em task "
                                    u"de RM") if e_rm else u"Dataset300 no disco",
                         "flag": not e_rm, "alerta": False,
                         "falta_peso": False},
                partes=[{"task": t, "parte": 1, "de": 1, "segundos": 12.5}])
            if e_rm:
                E._anotar_no_job(k.get("jid"), t, recuo_cpu={
                    "onde": u"parte 1/1", "prova": u"CUDA out of memory",
                    "segundos_na_placa": 3.0})
            return {"liver": 1}
        _dublar(E, "run_ts_task", _ts)
        _dublar(E, "regioes_no_campo",
                lambda masks, grade=None: (("abdome",), []))
        _dublar(E, "curar", _curar)
        _dublar(E, "para_oar", _para_oar)
        _dublar(E, "build_rtstruct", _rtst)
        _dublar(RO, "Saida", _Saida)
        def _registrar(*a, **k):
            chamadas.setdefault("registrar_serie", (a, dict(k)))
            casos[atual["uid"]] = k
            return ""
        _dublar(RG, "registrar_serie", _registrar)
        _dublar(RG, "medir_serie",
                lambda s, res=None, origem=u"": {
                    "marca": "medir_serie", "origem": origem,
                    "modalidade": (s or {}).get("modalidade")})
        L._CFG.clear()
        L._CFG.update({"incluir_nv": 0, "incluir_cads": 0, "incluir_moose": 0})
        series = L._com_escolhas_da_tela({"series": [
            {"uid": uid_ct, "pasta": os.path.join(base, paciente, "CT"),
             "modalidade": "CT", "pid": "F", "curto": "c",
             "modo": "perso", "protocolos": ["torax_mama"]},
            {"uid": uid_mr, "pasta": os.path.join(base, paciente, "MR"),
             "modalidade": "MR", "pid": "F", "curto": "m"}]})
        res = []
        for s in series:
            atual["uid"] = s["uid"]
            res.append(L._uma_serie(s, False, ["total_v3"], "auto", None, 60,
                                    60, None, marc, "BATERIA", 3600, 0.0))
    finally:
        for obj, nome, val in guardado.values():
            setattr(obj, nome, val)
        L._CFG.clear()
        L._CFG.update(velho_cfg)
        shutil.rmtree(base, ignore_errors=True)
    checar(u"as duas series foram ate o fim sem erro",
           all(not r.get("erro") for r in res),
           u" | ".join(str(r.get("erro"))[:100] for r in res))
    checar(u"a TC chega a porta do entregue (`radai_output.Saida`) como TC, "
           u"e a RM como RM",
           saidas.get(uid_ct) == "CT" and saidas.get(uid_mr) == "MR",
           str(saidas))
    checar(u"  e o lote NAO monta o entregue por fora dela (sem `para_oar` "
           u"nem `build_rtstruct` direto)",
           "para_oar" not in chamadas and "build_rtstruct" not in chamadas,
           str(sorted(chamadas)))
    checar(u"  e chama a porta unica, com o volume da serie",
           "full_e_oar" in chamadas
           and chamadas["full_e_oar"][1].get("volume_hu") is not None,
           str(sorted(chamadas)))
    checar(u"a TC com o protocolo Torax / Mama chega a `full_e_oar` com "
           u"torax=True; a RM sem ele, com None",
           torax_da_serie.get(uid_ct) is True
           and torax_da_serie.get(uid_mr) is None, str(torax_da_serie))
    c = casos.get(uid_mr) or {}
    serie = c.get("serie") or {}
    checar(u"o caso da RM e medido pela funcao COMUM, com a modalidade dela",
           serie.get("marca") == "medir_serie"
           and serie.get("origem") == u"rodar agora"
           and serie.get("modalidade") == "MR", str(serie))
    ex = c.get("execucao") or {}
    checar(u"o caso diz COMO rodou: origem, modalidade e dispositivo",
           ex.get("origem") == u"rodar agora" and ex.get("modalidade") == "MR"
           and ex.get("dispositivo_pedido") == "auto"
           and ex.get("dispositivo") == "cpu", str(ex))
    checar(u"  e a queda para a CPU chega aos fallbacks do caso",
           any(u"refazendo a task inteira em CPU" in f
               for f in (ex.get("fallbacks") or ())), str(ex.get("fallbacks")))
    checar(u"  e o tempo e o da serie, medido por quem rodou",
           isinstance(c.get("segundos_totais"), (int, float))
           and c.get("segundos_totais") == (res[1] or {}).get("segundos"),
           "%r %r" % (c.get("segundos_totais"), (res[1] or {}).get("segundos")))
    rc = ex.get("recorte_no_corpo") or {}
    checar(u"o recorte no corpo do caso e o que VALEU, lido do job: a RM "
           u"diz «nao se aplica»",
           (rc.get("total_mr") or {}).get("estado") == u"nao se aplica",
           str(rc))
    checar(u"  e a chave da estacao vai para `recorte_no_corpo_pedido` (sem "
           u"a chave injetada, o padrao do motor)",
           ex.get("recorte_no_corpo_pedido") is bool(E.RECORTE_NO_CORPO_PADRAO),
           str(ex.get("recorte_no_corpo_pedido")))
    checar(u"  o plano do motor chega ao caso: o modo que VALEU e o recuo "
           u"da placa", ex.get("modo") == "cpu"
           and ex.get("modo_do_plano") == "gpu"
           and (ex.get("recuo_cpu") or {}).get("onde") == u"parte 1/1",
           str(dict((k, ex.get(k)) for k in ("modo", "modo_do_plano",
                                               "recuo_cpu"))))
    checar(u"  e o tempo por parte, sem a nota de «nao expos»",
           (ex.get("tempo_por_parte") or [{}])[0].get("segundos") == 12.5
           and not ex.get("tempo_por_parte_nota"),
           str(ex.get("tempo_por_parte")))
    _esc = ex.get("escolha_da_serie") or {}
    _esc_ct = ((casos.get(uid_ct) or {}).get("execucao") or {}).get(
        "escolha_da_serie") or {}
    checar(u"  e a escolha da serie (a RM sem modo e AUTO; a TC no "
           u"PERSONALIZADO com o protocolo Torax / Mama)",
           _esc == {"modo": "auto"} and _esc_ct.get("modo") == "perso"
           and _esc_ct.get("protocolos") == ["torax_mama"]
           and "modo_da_serie" not in ex,
           u"RM=%s | TC=%s" % (_esc, _esc_ct))
    _pr = (casos.get(uid_ct) or {}).get("processamento") or {}
    checar(u"  e o caso leva o PROCESSAMENTO da v8.3 (spec T-RC): o modo, os "
           u"protocolos, as tasks ligadas e a comparacao",
           _pr.get("modo") == "perso"
           and _pr.get("protocolos") == ["torax_mama"]
           and "trunk_cavities" in (_pr.get("tasks_ligadas") or ())
           and _pr.get("comparacao") == {"ts": 0, "nv": 0, "cads": 0,
                                         "mse": 0}
           and "remocoes" not in _pr
           and isinstance(_pr.get("travamentos"), list), str(_pr)[:300])
    import radai_records as _RG
    checar(u"  com chaves que o registro conhece (nenhuma cai em "
           u"`campos_ignorados`)",
           not (set(_pr) - set(_RG.CAMPOS_DO_PROCESSAMENTO)), str(sorted(_pr)))
    fonte = lote_py_txt()
    checar(u"a copia da medida saiu do lote",
           u"def _serie_medida" not in fonte)

    trocar = list(c.get("so_trocar") or ())
    checar(u"o lote passa a pasta do paciente para ser TROCADA no registro",
           paciente in trocar, str(trocar)[:240])
    tmp = [p for p in re.split(r"[\\/]+", tempfile.gettempdir()) if len(p) >= 4]
    checar(u"  e nao a pasta temporaria, que estragaria todo «tempo» do log",
           not any(p.lower() == t.lower() for p in trocar for t in tmp),
           u"%s | %s" % (trocar, tmp))

    import inspect
    for nome in ("full_e_oar", "Saida", "registrar_serie"):
        a, k = chamadas.get(nome, ((), None))
        if k is None:
            checar(u"o lote chamou `%s`" % nome, False, str(sorted(chamadas)))
            continue
        try:
            inspect.signature(reais[nome]).bind(*a, **k)
            erro = u""
        except TypeError as e:
            erro = u"%s" % e
        checar(u"os argumentos que o lote passa a `%s` cabem na assinatura "
               u"real" % nome, not erro, erro)


def teste_a_rm_sem_modo_nao_roda_a_base_de_tc():
    secao(u"a RM sem modo nao roda a base de TC por cima da de RM")
    import engine as E
    import radai_tasks as RT
    import SimpleITK as sitk

    velho_cfg = dict(L._CFG)
    L._CFG.clear()
    linhas = []
    try:
        lista, _origem = L.tasks_iniciais({"modalidade": "MR"},
                                          ["total_v3", "head_glands_cavities"],
                                          log=linhas.append)
    finally:
        L._CFG.clear()
        L._CFG.update(velho_cfg)
    fam = set(RT.familia_da_task(t) for t in lista)
    checar(u"RM sem modo, TASKS=total_v3,head_glands_cavities: so a base de RM",
           len(lista) == 1 and RT.modalidade_da_base(lista[0]) == "MR",
           u"%s | %s" % (lista, fam))
    checar(u"  e o log diz o que trocou e o que saiu",
           any(u"e base de CT" in l for l in linhas)
           and any(u"head_glands_cavities e de CT; nao roda" in l for l in linhas),
           u" | ".join(linhas)[:300])

    base = tempfile.mkdtemp(prefix="radai_t_rmsem_")
    uid_mr = _serie(os.path.join(base, "PAC", "MR"), 3, 8, 3.0, "", "RM T1",
                    modalidade="MR")
    uid_ct = _serie(os.path.join(base, "PAC", "CT"), 2, 8, 3.0, "B30f", "TC")
    pedidas = {}
    atual = {"uid": ""}
    guardado = {}

    def _dublar(obj, nome, novo):
        guardado[(id(obj), nome)] = (obj, nome, getattr(obj, nome))
        setattr(obj, nome, novo)

    def _ref():
        img = sitk.Image(8, 8, 8, sitk.sitkInt16)
        img.SetSpacing((0.7, 0.7, 3.0))
        return img

    def _rtst(stage, masks, **kw):
        f = os.path.join(base, "rt_%s.dcm" % atual["uid"][-6:])
        io.open(f, "wb").write(b"RT")
        return f, {1: "Liver_ai"}

    class _Saida(object):
        def __init__(self, *a, **k):
            self.gravados = []
            self._a = a

        def full_e_oar(self, *a, **k):
            _rs_dublado(self, self._a[2], self._a[3])
            return {}

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
    import radai_output as RO
    import radai_records as RG

    def _rodar(uid, pasta, modalidade):
        atual["uid"] = uid
        pedidas[uid] = []
        s = {"uid": uid, "pasta": pasta, "modalidade": modalidade,
             "pid": "F", "curto": uid[-4:]}
        return L._uma_serie(s, False, ["total_v3"], "cpu", None, 60, 60,
                            None, marc, "BATERIA", 3600, 0.0)

    try:
        _dublar(E, "copy_sorted", lambda arqs, stage: None)
        _dublar(E, "load_sitk", lambda stage: _ref())
        _dublar(E, "_resolve_device", lambda d: "cpu")
        _dublar(E, "run_ts_task",
                lambda ref, t, **k: (pedidas.setdefault(atual["uid"], [])
                                     .append(t) or {"liver": 1}))
        _dublar(E, "regioes_no_campo", lambda masks, grade=None: ((), []))
        _dublar(E, "curar", lambda masks, cads, log=None: (masks, {}))
        _dublar(E, "para_oar", lambda masks, **k: masks)
        _dublar(E, "build_rtstruct", _rtst)
        _dublar(RO, "Saida", _Saida)
        _dublar(RG, "registrar_serie", lambda *a, **k: "")
        L._CFG.clear()
        L._CFG.update({"incluir_nv": 0, "incluir_cads": 0, "incluir_moose": 0})
        r_mr = _rodar(uid_mr, os.path.join(base, "PAC", "MR"), "MR")
        r_ct = _rodar(uid_ct, os.path.join(base, "PAC", "CT"), "CT")
        checar(u"as duas series foram ate o fim sem erro",
               not r_mr.get("erro") and not r_ct.get("erro"),
               u"%s | %s" % (r_mr.get("erro"), r_ct.get("erro")))
        pm = pedidas.get(uid_mr, [])
        checar(u"a RM sem modo pede SO a base de RM ao motor",
               len(pm) == 1 and RT.modalidade_da_base(pm[0]) == "MR", str(pm))
        checar(u"  e nenhuma task de TC depois dela (o masks.update trocaria "
               u"as estruturas)",
               not any(RT.modalidade_da_base(t) == "CT" for t in pm), str(pm))
        pc = pedidas.get(uid_ct, [])
        checar(u"a TC sem modo continua pedindo a base de TC",
               len(pc) == 1 and RT.modalidade_da_base(pc[0]) == "CT", str(pc))
        tem = hasattr(L, "_pela_modalidade")
        checar(u"  a regra da modalidade do lote e uma funcao "
               u"(`_pela_modalidade`)", tem)
        if tem:
            _dublar(L, "_pela_modalidade",
                    lambda tasks, modalidade, log=None: tuple(tasks))
            _rodar(uid_mr, os.path.join(base, "PAC", "MR"), "MR")
            pi = pedidas.get(uid_mr, [])
            checar(u"  isca: com a lista como veio, a RM pede a base de TC "
                   u"por cima (a checagem discrimina)",
                   any(RT.modalidade_da_base(t) == "CT" for t in pi), str(pi))
    finally:
        for obj, nome, val in guardado.values():
            setattr(obj, nome, val)
        L._CFG.clear()
        L._CFG.update(velho_cfg)
        shutil.rmtree(base, ignore_errors=True)


def teste_o_erro_do_zip_nao_leva_o_paciente_ao_log():
    secao(u"o erro do .zip vai ao log sem o paciente")
    import radai_viewseg as V
    import radai_thumbnail as TH
    linhas = []
    velho_log, velho_res = TH._log_da_estacao, V.radai_batch.resolver_pasta
    TH._log_da_estacao = lambda: linhas.append
    casos = (
        (u"Não consegui extrair: File 'ISCA BELTRANO 12345/CT/IM0001.dcm' is "
         u"encrypted, password required for extraction",
         u"OUTRA PESSOA FANTOMA/CT", u"C:\\EXAMES\\exame_cifrado.zip",
         u"o membro cifrado nao leva o nome (ele esta em outra pasta do .zip)"),
        (u"Não achei o arquivo C:\\EXAMES\\ISCA BELTRANO 12345\\exame.zip.",
         u"CT", u"C:\\EXAMES\\ISCA BELTRANO 12345\\exame.zip",
         u"o .zip que sumiu nao leva a pasta com espaco"),
        (u"O .zip não tem nenhum arquivo que possa ser imagem: ISCA BELTRANO 12345/CT",
         u"ISCA BELTRANO 12345/CT", u"C:\\EXAMES\\pacote.zip",
         u"a pasta de dentro do .zip e trocada"),
    )
    try:
        for k, (erro, pasta, zip_, rotulo) in enumerate(casos):
            V.radai_batch.resolver_pasta = (lambda s, _e=erro: ("", _e))
            del linhas[:]
            r = V.abrir_um_eixo(pasta, zip_, "1.9.999.%d" % (7000 + k))
            texto = u"\n".join(linhas)
            sobra = [x for x in (u"ISCA", u"BELTRANO", u"12345") if x in texto]
            checar(rotulo, bool(linhas) and not sobra,
                   u"%s | %s" % (sobra, texto[-220:]))
            checar(u"  e a tela recebe a frase fixa",
                   r == {"erro": u"não achei a pasta da série"}, str(r))
        V.radai_batch.resolver_pasta = (lambda s: ("", casos[0][0]))
        del linhas[:]
        V.abrir_um_eixo(casos[0][1], casos[0][2], "1.9.999.7999")
        checar(u"a frase fixa do nosso lado continua no log",
               u"Não consegui extrair" in u"\n".join(linhas), u"\n".join(linhas)[-200:])
    finally:
        TH._log_da_estacao = velho_log
        V.radai_batch.resolver_pasta = velho_res


def teste_o_explorador_nao_devolve_o_caminho_no_erro():
    secao(u"o explorador nao devolve o caminho no erro")
    import json as _json
    pasta = tempfile.mkdtemp(prefix="radai_t_explorador_")
    orig = L.os.scandir

    def _cai(caminho):
        raise OSError(64, u"O nome da rede especificado não está mais "
                          u"disponível", caminho + u"\\ISCA BELTRANO 12345")
    try:
        L.os.scandir = _cai
        d = L.listar_pastas_do_explorador(pasta, teto_s=10.0)
    finally:
        L.os.scandir = orig
        shutil.rmtree(pasta, ignore_errors=True)
    cru = _json.dumps(d, ensure_ascii=False)
    checar(u"a frase e fixa", d.get("erro") == u"a pasta não pôde ser listada",
           cru[:200])
    checar(u"  e a classe do erro vem num campo a parte",
           d.get("tipo") == "OSError", cru[:200])
    checar(u"  e o caminho nao volta", u"ISCA" not in cru
           and u"BELTRANO" not in cru
           and pasta not in cru.replace(u"\\\\", u"\\"), cru[:200])
    import radai_ui as _U
    corpo = _U.COMPONENTES_JS
    corpo = corpo[corpo.index(u"function fpLista("):]
    corpo = corpo[:corpo.index(u"\n function ")]
    checar(u"a tela (o explorador da casca, que o Rodar agora usa) poe a classe "
           u"num <code>, fora da frase que se traduz",
           u"d.tipo" in corpo and u"<code>" in corpo, corpo[:120])
    checar(u"  e o Rodar agora não tem mais seletor próprio",
           u"function fpPintarLista(" not in lote_py_txt())


def teste_a_fila_que_nao_se_le_nao_e_vazia():
    secao(u"a fila que nao se le nao e vazia")
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    import radai_queue_state as F
    app = FastAPI()
    L.montar(app, {"tasks": ["total_v3"], "device": "cpu"})
    cli = TestClient(app)
    orig = F.series_esperando

    def _quebrada():
        raise RuntimeError(u"estado da fila ilegivel (dublado)")
    try:
        F.series_esperando = _quebrada
        p1 = cli.post("/api/pipeline/iniciar").json()
        F.series_esperando = lambda: []
        v1 = cli.post("/api/pipeline/iniciar").json()
    finally:
        F.series_esperando = orig
        try:
            L.pausar(False)
        except Exception:
            pass
    checar(u"/api/pipeline/iniciar: a fila que levanta devolve o erro, e "
           u"nao «vazia»",
           u"RuntimeError" in (p1.get("erro") or u"")
           and u"vazia" not in (p1.get("erro") or u"")
           and not p1.get("ok"), str(p1))
    checar(u"/api/pipeline/iniciar: e a lista vazia de verdade continua "
           u"dizendo «vazia»",
           u"vazia" in (v1.get("erro") or u"") and not v1.get("ok"), str(v1))
    vivas = set((m, getattr(r, "path", u"")) for r in app.routes
                for m in (getattr(r, "methods", None) or ()))
    mortas = (("POST", u"/api/lote/previa"), ("POST", u"/api/lote/iniciar"),
              ("POST", u"/api/lote/revisao"), ("POST", u"/api/lote/estruturas"),
              ("POST", u"/api/lote/mpr"), ("GET", u"/api/lote/imagem"),
              ("GET", u"/api/lote/estado"), ("POST", u"/api/lote/cancelar"),
              ("POST", u"/api/lote/varrer"))
    checar(u"as rotas sem tela que as chame sairam (a previa de um corte, o "
           u"iniciar da demo, a revisao, as estruturas, o MPR e a imagem "
           u"dele, o estado e o cancelar do lote, o POST unico da varredura)",
           not [r for r in mortas if r in vivas],
           str([r for r in mortas if r in vivas]))
    import radai_varrer as _V
    checar(u"  e o «Rodar agora» continua com o que a tela chama (a "
           u"varredura da casca no uso «lote»)",
           ("POST", u"/api/pipeline/iniciar") in vivas
           and ("POST", u"/api/pipeline/cancelar") in vivas
           and _V.uso("lote") is not None
           and u"uiVarrer({uso: 'lote'" in L._pagina(), str(sorted(
               p for m, p in vivas if p.startswith(u"/api/lote"))))
    import radai_models as _RM
    checar(u"o radai_models nao monta rota (nenhuma tela lista, escolhe ou "
           u"baixa modelo)", not hasattr(_RM, "montar"))


def teste_o_registro_de_casos_fica_isolado():
    secao(u"o registro de casos fica fora do repositorio")
    import radai_records
    raiz = os.path.abspath(radai_records.raiz())
    temp = os.path.abspath(os.environ.get("RADAI_REGISTRO_DIR") or u"")
    checar(u"a raiz do registro e a temporaria desta bateria",
           bool(temp) and raiz == temp, u"%s" % raiz)
    checar(u"  e nao fica dentro do repositorio",
           not os.path.normcase(raiz).startswith(
               os.path.normcase(os.path.abspath(RAIZ)) + os.sep), raiz)
    nomes_antes, linhas_antes = _CASOS_ANTES
    nomes_depois, linhas_depois = _casos_do_repositorio()
    novos = sorted(nomes_depois - nomes_antes)
    checar(u"app\\registro\\casos nao ganhou caso nesta execucao",
           not novos, u"%d novo(s): %s" % (len(novos), u", ".join(novos[:3])))
    checar(u"  e o indice de app\\registro nao ganhou linha",
           linhas_depois <= linhas_antes,
           u"%d -> %d" % (linhas_antes, linhas_depois))
    try:
        gravados = os.listdir(os.path.join(temp, "casos"))
    except OSError:
        gravados = []
    checar(u"a bateria chegou ao registro (%d caso(s) na temporaria)"
           % len(gravados), len(gravados) >= 1,
           u"sem caso gravado, as duas de cima nao provam nada")


def teste_o_batimento_do_lote_olha_o_que_renovar_devolve():
    secao(u"o batimento do lote olha o False de `renovar`")
    import threading as _th
    checar(u"a politica e uma funcao de modulo (`bater_lock`)",
           callable(getattr(L, "bater_lock", None)))
    if not callable(getattr(L, "bater_lock", None)):
        return

    def _rodar(respostas, bater=None):
        linhas, fila = [], list(respostas)
        parar = _th.Event()

        def _renovar(pasta, uid):
            if not fila:
                parar.set()
                return True
            r = fila.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        (bater or L.bater_lock)(_renovar, "p", "1.2.3.456789012", parar,
                                0.001, linhas.append)
        return linhas

    l1 = _rodar([True, False, False, False, True])
    avisos = [l for l in l1 if u"NAO consigo gravar o sinal de vida" in l]
    voltas = [l for l in l1 if u"voltou a ser gravado" in l]
    checar(u"a SEGUNDA falha seguida avisa -- uma vez so, nao a cada volta",
           len(avisos) == 1, u" | ".join(l1))
    checar(u"  e a volta diz quantas vezes falhou",
           len(voltas) == 1 and u"3 vez(es)" in voltas[0], u" | ".join(l1))
    checar(u"  e o recado leva so os 8 ultimos do UID",
           avisos and u"...56789012" in avisos[0]
           and u"1.2.3.456789012" not in avisos[0], avisos and avisos[0])
    l2 = _rodar([True, False, True, False, True])
    checar(u"UMA falha solta nao vale linha (a margem existe para isso)",
           not l2, u" | ".join(l2))
    l3 = _rodar([OSError("share caiu"), OSError("share caiu"), True])
    checar(u"a excecao de `renovar` conta como falha, e nao derruba o batimento",
           any(u"NAO consigo" in l for l in l3), u" | ".join(l3))

    def _velho(renovar, pasta, uid, parar, intervalo_s, log=None):
        while not parar.is_set():
            try:
                renovar(pasta, uid)
            except Exception:
                pass
            parar.wait(intervalo_s)
    l4 = _rodar([True, False, False, False, True], bater=_velho)
    checar(u"(isca) o batimento que ignora o retorno fica calado -- a "
           u"checagem discrimina", not l4, u" | ".join(l4))

    def _ordem_no_finally(fonte):
        import ast as _ast
        arv = _ast.parse(fonte)
        for no in _ast.walk(arv):
            if isinstance(no, _ast.FunctionDef) and no.name == "_uma_serie":
                for t in _ast.walk(no):
                    if isinstance(t, _ast.Try) and t.finalbody:
                        j = u = None
                        for s in t.finalbody:
                            for c in _ast.walk(s):
                                if isinstance(c, _ast.Call):
                                    f = c.func
                                    if (getattr(f, "attr", None) == "join"
                                            and getattr(getattr(f, "value",
                                                                None), "id",
                                                        None) == "_hb"):
                                        j = j or c.lineno
                                if (isinstance(c, _ast.Subscript)
                                        and isinstance(c.slice, _ast.Constant)
                                        and c.slice.value == "unclaim"):
                                    u = u or c.lineno
                        if u is not None:
                            return j, u
        return None, None
    fonte = lote_py_txt()
    j, u = _ordem_no_finally(fonte)
    checar(u"o `finally` de `_uma_serie` faz `join` do batimento ANTES do "
           u"`unclaim`", j is not None and u is not None and j < u,
           u"join=%s unclaim=%s" % (j, u))
    _sem = fonte.replace(u"_hb.join(timeout=30.0)", u"pass")
    j2, u2 = _ordem_no_finally(_sem)
    checar(u"  (isca) sem o `join`, a leitura acusa", j2 is None,
           u"join=%s" % j2)


def teste_a_primeira_entrega_vale_no_lote():
    secao(u"a primeira entrega vale, no lote tambem")
    import ast as _ast
    import inspect
    import threading as _th
    import engine as E
    import radai_output as RO
    import radai_records as RG
    import SimpleITK as sitk

    batidas = []
    parar = _th.Event()
    voltas = [0]

    def _renovar(p, u):
        voltas[0] += 1
        if voltas[0] >= 4:
            parar.set()
        return True
    L.bater_lock(_renovar, "p", "1.2.3", parar, 0.001, None,
                 entrega=lambda: batidas.append(1))
    checar(u"`bater_lock` bate a reserva de entrega a cada volta",
           len(batidas) == voltas[0], u"%d batidas em %d voltas"
           % (len(batidas), voltas[0]))
    p2, n2 = _th.Event(), [0]

    def _renovar2(p, u):
        n2[0] += 1
        if n2[0] >= 3:
            p2.set()
        return True
    checar(u"  e a batida que levanta nao derruba o batimento",
           L.bater_lock(_renovar2, "p", "1.2.3", p2, 0.001, None,
                        entrega=lambda: 1 / 0) is None and n2[0] >= 3,
           str(n2))

    def _thread_leva_entrega(fonte):
        arv = _ast.parse(fonte)
        for no in _ast.walk(arv):
            if isinstance(no, _ast.FunctionDef) and no.name == "_uma_serie":
                for c in _ast.walk(no):
                    if (isinstance(c, _ast.Call)
                            and getattr(c.func, "attr", "") == "Thread"):
                        for k in c.keywords:
                            if (k.arg == "kwargs"
                                    and isinstance(k.value, _ast.Dict)
                                    and any(getattr(x, "value", None)
                                            == "entrega"
                                            for x in k.value.keys)):
                                return True
        return False
    fonte = lote_py_txt()
    checar(u"o batimento de `_uma_serie` recebe a batida da reserva",
           _thread_leva_entrega(fonte))
    checar(u"  (isca) sem o `kwargs`, a leitura acusa",
           not _thread_leva_entrega(fonte.replace(
               u'kwargs={"entrega": _bater_entrega},', u"")))

    linhas = []
    r = L.reservar_a_entrega({}, "p", "1.2.3.45678901", linhas.append)
    checar(u"sem `reservar_entrega` injetada (vigia de antes): publica, e "
           u"DIZ que nao conferiu", r == (True, False, u"")
           and any(u"sem a reserva de entrega" in l for l in linhas),
           str(r))
    r = L.reservar_a_entrega(
        {"reservar_entrega": lambda p, u: 1 / 0}, "p", "1.2.3", None)
    checar(u"a reserva que levanta conta como «nao pode» (o vigia faz o "
           u"mesmo consigo)", r[0] is False and u"ZeroDivisionError" in r[2],
           str(r))

    base = tempfile.mkdtemp(prefix="radai_t_entrega_")
    pasta = os.path.join(base, "PAC", "CT")
    uid = _serie(pasta, 2, 8, 3.0, "B30f", "TC")
    guardado = {}

    def _dublar(obj, nome, novo):
        guardado[(id(obj), nome)] = (obj, nome, getattr(obj, nome))
        setattr(obj, nome, novo)

    def _ref():
        img = sitk.Image(8, 8, 8, sitk.sitkInt16)
        img.SetSpacing((0.7, 0.7, 3.0))
        return img

    estado = {"eventos": [], "feita": False, "meu": (True, "ESTA"),
              "levanta": False}

    class _Saida(object):
        def __init__(self, *a, **k):
            estado["eventos"].append("Saida")
            self.gravados = []
            self._a = a

        def full_e_oar(self, *a, **k):
            estado["eventos"].append("full_e_oar")
            if estado.get("dorme"):
                import time as _tm
                _tm.sleep(estado["dorme"])
            if estado["levanta"]:
                raise RuntimeError("a cadeia do FULL levantou")
            _rs_dublado(self, self._a[2], self._a[3])
            return {"estruturas": ["Liver_ai"], "oar": "", "full": ""}

        def __getattr__(self, nome):
            return lambda *a, **k: None

    class _Marca(object):
        def __init__(self, tipo):
            self.tipo = tipo

        def write_text(self, *a, **k):
            estado["eventos"].append(self.tipo)
            return 0

    def _marcadores(reserva):
        ev = estado["eventos"]
        m = {"has_marker": lambda p, u, k: k == "done" and estado["feita"],
             "read_marker": lambda p, u, k: (
                 {"machine": "BATERIA"} if k == "lock"
                 else ({"machine": estado.get("dono_entrega", "OUTRA")}
                       if estado.get("dono_entrega", "OUTRA") else None)),
             "claim": lambda *a, **k: True,
             "unclaim": lambda *a, **k: ev.append("unclaim"),
             "renovar": lambda *a, **k: True,
             "m_path": lambda p, u, k, criar=False: _Marca(k),
             "lock_e_meu": lambda p, u: estado["meu"],
             "soltar_entrega": lambda p, u: ev.append("soltar")}
        if estado.get("com_renovar"):
            m["renovar_entrega"] = (lambda p, u: ev.append("renovar_entrega")
                                    or True)
        if reserva is not None:
            def _reservar(p, u):
                ev.append("reservar")
                if isinstance(reserva, Exception):
                    raise reserva
                return reserva
            m["reservar_entrega"] = _reservar
        return m

    def _rodar(reserva, fn=None, hb=3600, **muda):
        estado.update({"eventos": [], "feita": False, "meu": (True, "ESTA"),
                       "levanta": False, "dorme": 0, "com_renovar": False,
                       "dono_entrega": "OUTRA"})
        estado.update(muda)
        log = []
        s = {"uid": uid, "pasta": pasta, "modalidade": "CT", "pid": "F",
             "curto": "c"}
        r = (fn or L._uma_serie)(s, False, ["total_v3"], "cpu", None, 60, 60,
                                 log.append, _marcadores(reserva),
                                 "BATERIA", hb, 0.0)
        return r, list(estado["eventos"]), log

    velho_cfg = dict(L._CFG)
    try:
        _dublar(E, "copy_sorted", lambda arqs, stage: None)
        _dublar(E, "load_sitk", lambda stage: _ref())
        _dublar(E, "_resolve_device", lambda d: "cpu")
        _dublar(E, "run_ts_task", lambda ref, t, **k: {"liver": 1})
        _dublar(E, "regioes_no_campo",
                lambda masks, grade=None: (("abdome",), []))
        _dublar(RO, "Saida", _Saida)
        _dublar(RG, "registrar_serie", lambda *a, **k: "")
        _dublar(RG, "medir_serie", lambda *a, **k: {})
        L._CFG.clear()
        L._CFG.update({"incluir_nv": 0, "incluir_cads": 0, "incluir_moose": 0})

        ocupada = (False, u"`OUTRA` esta gravando esta serie agora — a "
                          u"primeira entrega vale")
        r, ev, log = _rodar(ocupada)
        checar(u"outra estacao gravando: NADA e publicado (nem a porta do "
               u"entregue e aberta)", "Saida" not in ev
               and "full_e_oar" not in ev and "done" not in ev, str(ev))
        checar(u"  e nao e falha: pulada, com o motivo e o nome de quem grava",
               not r.get("erro") and r.get("pulo") == "outra"
               and u"primeira entrega vale" in r.get("pulada", "")
               and r.get("dono") == "OUTRA", str(r)[:300])
        checar(u"  e o log diz DESCARTADA, sem contar como falha",
               any(u"DESCARTADA" in l and u"nao conta como falha" in l
                   for l in log), u" | ".join(log[-3:]))
        checar(u"  e a reserva que nao foi nossa nao e solta; o lock sai",
               "soltar" not in ev and "unclaim" in ev, str(ev))
        r, ev, log = _rodar(ocupada, dono_entrega="")
        checar(u"  sem a reserva legivel, o nome sai do motivo (`OUTRA`)",
               r.get("dono") == "OUTRA", str(r.get("dono")))
        r, ev, log = _rodar((False, u"nao consegui reservar a entrega"),
                            dono_entrega="")
        checar(u"  sem nome em lugar nenhum, o dono fica vazio (e nunca e o "
               u"desta estacao)", r.get("dono") == "", str(r.get("dono")))
        _src_us = inspect.getsource(L._uma_serie)
        _alvo_dono = u'res["dono"] = _dono_da_entrega(s, marcadores, str(e),'
        ns_d = dict(vars(L))
        exec(compile(_src_us.replace(
            _alvo_dono, u'res["dono"] = _dono_do_lock(s, marcadores) or (s,'),
            "<isca-dono>", "exec"), ns_d)
        r, ev, log = _rodar(ocupada, fn=ns_d["_uma_serie"])
        checar(u"  (isca) com o dono lido do NOSSO lock, o card diria o nome "
               u"desta estacao -- a checagem discrimina",
               _alvo_dono in _src_us and r.get("dono") == "BATERIA",
               str(r.get("dono")))
        _orig = _marcadores

        def _com_done(reserva):
            m = _orig(reserva)
            m["has_marker"] = (lambda p, u, k: k == "done"
                               and "reservar" in estado["eventos"])
            return m
        _marcadores = _com_done
        try:
            r3, ev3, _l3 = _rodar((False, u"a serie ja foi entregue por "
                                          u"`OUTRA`"))
        finally:
            _marcadores = _orig
        checar(u"com o `done` da outra no disco, o desfecho e «ja concluida»",
               r3.get("pulo") == "concluida" and "full_e_oar" not in ev3,
               str(r3)[:200])
        r, ev, log = _rodar((True, u""), meu=(False, "OUTRA"))
        checar(u"reservou: publica", "full_e_oar" in ev and not r.get("erro"),
               str(r.get("erro")))
        checar(u"  e o log diz que o lock e de outra e que a primeira "
               u"entrega vale", any(u"o lock agora e de `OUTRA`" in l
                                    for l in log), u" | ".join(log[-4:]))
        checar(u"  e a ORDEM: reserva antes da porta; `done`, depois solta a "
               u"reserva, depois o lock",
               ev.index("reservar") < ev.index("Saida")
               < ev.index("done") < ev.index("soltar") < ev.index("unclaim")
               and ev.count("soltar") == 1, str(ev))
        r, ev, log = _rodar((True, u""), levanta=True)
        checar(u"a serie que morre depois de reservar solta a reserva no "
               u"`finally`, antes do lock", bool(r.get("erro"))
               and "done" not in ev and "soltar" in ev
               and ev.index("soltar") < ev.index("unclaim"), str(ev))
        r, ev, log = _rodar(None)
        checar(u"sem a chave (vigia de antes): publica como antes, e diz",
               "full_e_oar" in ev and "soltar" not in ev
               and any(u"sem a reserva de entrega" in l for l in log),
               str(ev))
        r, ev, log = _rodar(RuntimeError("share caiu"))
        checar(u"a reserva que levanta: nada publicado, pulada e nao falha",
               "full_e_oar" not in ev and not r.get("erro")
               and r.get("pulo") == "outra", str(r)[:200])

        r, ev, log = _rodar((True, u""), hb=0.01, dorme=0.3, com_renovar=True)
        _bat = [k for k, x in enumerate(ev) if x == "renovar_entrega"]
        checar(u"com `renovar_entrega` injetada, o batimento renova a reserva "
               u"enquanto a publicacao dura",
               len(_bat) >= 2 and not r.get("erro"),
               u"%d batida(s); %s" % (len(_bat), r.get("erro")))
        checar(u"  e so' entre a reserva e a soltura (nada a bater antes, nada "
               u"depois)", bool(_bat) and "reservar" in ev and "soltar" in ev
               and ev.index("reservar") < _bat[0]
               and _bat[-1] < ev.index("soltar"),
               str([x for x in ev if x != "renovar_entrega"]))
        _src_b = inspect.getsource(L._uma_serie)
        _alvo_b = u'_renovar_entrega = marcadores.get("renovar_entrega")'
        checar(u"  (isca) a leitura da batida esta onde a isca a procura",
               _alvo_b in _src_b)
        _ns_b = dict(vars(L))
        exec(compile(_src_b.replace(_alvo_b, u"_renovar_entrega = None"),
                     "<isca-batida>", "exec"), _ns_b)
        r, ev, log = _rodar((True, u""), fn=_ns_b["_uma_serie"], hb=0.01,
                            dorme=0.3, com_renovar=True)
        checar(u"  (isca) sem ler a funcao, nenhuma batida -- a checagem "
               u"discrimina", "renovar_entrega" not in ev
               and "full_e_oar" in ev, str(ev.count("renovar_entrega")))

        src = inspect.getsource(L._uma_serie)
        alvo = (u'_pode, _entrega["reservada"], _porque = reservar_a_entrega(\n'
                u'            marcadores, s["pasta"], s["uid"], log)')
        checar(u"(isca) a linha da reserva esta onde a isca a procura",
               alvo in src)
        ns = dict(vars(L))
        exec(compile(src.replace(alvo, u'_pode, _entrega["reservada"], '
                                       u'_porque = True, False, ""'),
                     "<isca>", "exec"), ns)
        r, ev, log = _rodar(ocupada, fn=ns["_uma_serie"])
        checar(u"  (isca) sem a reserva, o lote publica por cima de quem "
               u"esta gravando -- a checagem discrimina",
               "full_e_oar" in ev, str(ev))
    finally:
        for obj, nome, val in guardado.values():
            setattr(obj, nome, val)
        L._CFG.clear()
        L._CFG.update(velho_cfg)
        shutil.rmtree(base, ignore_errors=True)


def _duas_series_na_mesma_pasta(base):
    pasta = os.path.join(base, "PAC", "CT")
    os.makedirs(pasta)
    uids = []
    for letra, n in (("A", 2), ("B", 3)):
        cru = os.path.join(base, "cru_" + letra)
        uids.append(_serie(cru, n, 8, 3.0, "B30f", "TC"))
        for nome in os.listdir(cru):
            shutil.move(os.path.join(cru, nome),
                        os.path.join(pasta, letra + "_" + nome))
    return pasta, uids[0], uids[1]


def teste_rodar_agora_nao_apaga_a_entrega_de_outra_serie_da_pasta():
    secao(u"o Rodar agora nao apaga a entrega de outra serie da pasta")
    import inspect
    import engine as E
    import radai_output as RO
    import radai_records as RG
    import radai_sets as RS
    import SimpleITK as sitk

    nomes = ["RS_RadAI_20260101_AAAA1111.dcm",
             "RS_RadAI_FULL_20260101_AAAA1111.dcm",
             "RS_RadAI_20260101_BBBB2222.dcm",
             "RS_RadAI_TS_20260101_bbbb2222.DCM",
             "RS_OutroSistema_BBBB2222.dcm", "IM00001"]
    checar(u"`arquivos_da_serie` fica so com os nossos DESTA serie (o sufixo "
           u"`_<uid8>.dcm`, sem diferenciar maiuscula)",
           RS.arquivos_da_serie(nomes, "1.2.3.BBBB2222")
           == ["RS_RadAI_20260101_BBBB2222.dcm",
               "RS_RadAI_TS_20260101_bbbb2222.DCM"],
           str(RS.arquivos_da_serie(nomes, "1.2.3.BBBB2222")))
    checar(u"  e sem UID nao devolve nada (nao se apaga por «nao sei»)",
           RS.arquivos_da_serie(nomes, "") == [])

    base = tempfile.mkdtemp(prefix="radai_t_2series_")
    pasta, uid_a, uid_b = _duas_series_na_mesma_pasta(base)
    a8, b8 = uid_a[-8:], uid_b[-8:]
    entrega_a = ["RS_RadAI_20260101_%s.dcm" % a8,
                 "RS_RadAI_FULL_20260101_%s.dcm" % a8]
    velho_b = "RS_RadAI_TS_20260101_%s.dcm" % b8
    guardado = {}

    def _dublar(obj, nome, novo):
        guardado[(id(obj), nome)] = (obj, nome, getattr(obj, nome))
        setattr(obj, nome, novo)

    def _ref():
        img = sitk.Image(8, 8, 8, sitk.sitkInt16)
        img.SetSpacing((0.7, 0.7, 3.0))
        return img

    _alvo_de_verdade = RO.Saida._alvo

    class _Saida(object):
        def __init__(self, engine, stage, destino, rs_name, *a, **k):
            self.destino, self.rs_name = destino, rs_name
            self.gravados = []

        def _alvo(self, infixo):
            return _alvo_de_verdade(self, infixo)

        def full_e_oar(self, *a, **k):
            for cod in ("oar", "full"):
                alvo = self._alvo(RS.POR_COD[cod]["infixo"])
                io.open(alvo, "wb").write(b"novo")
                self.gravados.append(cod)
            return {"estruturas": ["Liver_ai"], "oar": "", "full": ""}

        def __getattr__(self, nome):
            return lambda *a, **k: None

    class _Marca(object):
        def write_text(self, *a, **k):
            return 0

    marcadores = {"has_marker": lambda p, u, k: False,
                  "read_marker": lambda p, u, k: None,
                  "claim": lambda *a, **k: True,
                  "unclaim": lambda *a, **k: None,
                  "renovar": lambda *a, **k: True,
                  "m_path": lambda p, u, k, criar=False: _Marca()}

    def _preparar():
        for n in os.listdir(pasta):
            if n.startswith("RS_RadAI_"):
                os.remove(os.path.join(pasta, n))
        for n in entrega_a + [velho_b]:
            io.open(os.path.join(pasta, n), "wb").write(b"velho")

    def _rodar_b(fn=None):
        _preparar()
        log = []
        s = {"uid": uid_b, "pasta": pasta, "modalidade": "CT", "pid": "F",
             "curto": b8, "date": "20260101", "modo": "auto"}
        r = (fn or L._uma_serie)(s, False, ["total_v3"], "cpu", None, 60, 60,
                                 log.append, marcadores, "BATERIA", 3600, 0.0)
        return r, sorted(n for n in os.listdir(pasta)
                         if n.startswith("RS_RadAI_")), log

    velho_cfg = dict(L._CFG)
    try:
        _preparar()
        por_uid = dict((s["uid"], s) for s in L.varrer(pasta, min_cortes=5))
        checar(u"a varredura acha as duas series na MESMA pasta",
               set(por_uid) == set([uid_a, uid_b])
               and por_uid[uid_a]["pasta"] == por_uid[uid_b]["pasta"],
               str(sorted(por_uid)))
        if set(por_uid) == set([uid_a, uid_b]):
            checar(u"  a serie A diz os arquivos DELA, e so eles",
                   sorted(por_uid[uid_a].get("radai_na_pasta") or [])
                   == sorted(entrega_a) and por_uid[uid_a].get("tem_rs"),
                   str(por_uid[uid_a].get("radai_na_pasta")))
            checar(u"  e a B nao herda a entrega da A (so o arquivo velho "
                   u"dela mesma)",
                   por_uid[uid_b].get("radai_na_pasta") == [velho_b],
                   str(por_uid[uid_b].get("radai_na_pasta")))

        _dublar(E, "copy_sorted", lambda arqs, stage: None)
        _dublar(E, "load_sitk", lambda stage: _ref())
        _dublar(E, "_resolve_device", lambda d: "cpu")
        _dublar(E, "run_ts_task", lambda ref, t, **k: {"liver": 1})
        _dublar(E, "regioes_no_campo",
                lambda masks, grade=None: (("abdome",), []))
        _dublar(RO, "Saida", _Saida)
        _dublar(RG, "registrar_serie", lambda *a, **k: "")
        _dublar(RG, "medir_serie", lambda *a, **k: {})
        L._CFG.clear()
        L._CFG.update({"incluir_nv": 0, "incluir_cads": 0, "incluir_moose": 0})

        r, depois, log = _rodar_b()
        checar(u"a serie B rodou (o duble gravou o OAR e o FULL dela)",
               not r.get("erro") and not r.get("pulada")
               and ("RS_RadAI_FULL_20260101_%s.dcm" % b8) in depois,
               u"%s | %s" % (r.get("erro") or r.get("pulada"), depois))
        checar(u"rodar a B NAO apaga o OAR nem o FULL da A, da mesma pasta",
               all(n in depois for n in entrega_a), str(depois))
        checar(u"  e o que era da propria B e nao foi refeito sai (a "
               u"substituicao continua valendo para a serie)",
               velho_b not in depois, str(depois))
        checar(u"  e o log conta so os arquivos da B",
               any(u"substituindo: 0 arquivo(s)" in l and u"1 apagados" in l
                   and a8 not in l for l in log),
               u" | ".join(l for l in log if u"substitu" in l))

        src = inspect.getsource(L._uma_serie)
        alvo = u'_rs_da_serie(s["pasta"], s["uid"])'
        checar(u"(isca) a lista filtrada esta onde a isca a procura",
               src.count(alvo) == 1)
        ns = dict(vars(L))
        exec(compile(src.replace(alvo, u'_rs_existente(s["pasta"])'),
                     "<isca-2series>", "exec"), ns)
        r, depois, log = _rodar_b(fn=ns["_uma_serie"])
        checar(u"  (isca) com a pasta inteira, a entrega da A some -- a "
               u"checagem discrimina",
               not r.get("erro") and not any(n in depois for n in entrega_a),
               str(depois))
    finally:
        for obj, nome, val in guardado.values():
            setattr(obj, nome, val)
        L._CFG.clear()
        L._CFG.update(velho_cfg)
        shutil.rmtree(base, ignore_errors=True)


def _marcadores_em_disco(eventos, reserva_recusa=None):
    import json as _j
    import pathlib as _pl

    def m_path(p, u, k, criar=False):
        d = os.path.join(str(p), "_RadAI")
        if criar:
            os.makedirs(d, exist_ok=True)
        return _pl.Path(d, "%s.%s.json" % (u, k))

    def has(p, u, k):
        return m_path(p, u, k).exists()

    def ler(p, u, k):
        try:
            return _j.loads(m_path(p, u, k).read_text(encoding="utf-8"))
        except Exception:
            return None

    def claim(p, u, info):
        eventos.append("claim")
        m_path(p, u, "lock", criar=True).write_text(_j.dumps(info))
        return True

    def unclaim(p, u):
        eventos.append("unclaim")
        try:
            m_path(p, u, "lock").unlink()
        except Exception:
            pass

    def reservar(p, u):
        eventos.append("reservar:%s" % ("com_done" if has(p, u, "done")
                                        else "sem_done"))
        if reserva_recusa:
            return False, reserva_recusa
        if has(p, u, "done"):
            return False, (u"a serie ja foi entregue por `OUTRA` — a "
                           u"primeira entrega vale")
        m_path(p, u, "entrega", criar=True).write_text(u"{}")
        return True, u""

    def soltar(p, u):
        eventos.append("soltar")
        try:
            m_path(p, u, "entrega").unlink()
        except Exception:
            pass

    def resolver(p, u):
        eventos.append("resolver")
        d = os.path.join(str(p), "_RadAI")
        try:
            nomes = [n for n in os.listdir(d)
                     if n.startswith("%s.done.json.substituido." % u)]
        except OSError:
            return ""
        if not nomes or has(p, u, "lock") or has(p, u, "done"):
            return ""
        os.replace(os.path.join(d, nomes[0]), str(m_path(p, u, "done")))
        return "devolvido"

    return {"has_marker": has, "read_marker": ler, "claim": claim,
            "unclaim": unclaim, "renovar": lambda *a, **k: True,
            "m_path": m_path, "reservar_entrega": reservar,
            "soltar_entrega": soltar, "lock_e_meu": lambda p, u: (True, ""),
            "resolver_done_afastado": resolver}


def _linha_cabe(pagina):
    acoes = (u"td.acoes .acoes-bts{display:inline-flex;flex-wrap:wrap" in pagina
             and u"'<td class=\"acoes\"><span class=\"acoes-bts\">'+bt+ver" in pagina
             and u"td.acoes{white-space:nowrap" not in pagina)
    desc = (u"-webkit-line-clamp:2" in pagina
            and u"'<td class=\"desc\"><div class=\"desc-cx\"><span class=\"desc-t\"" in pagina)
    return acoes, desc


def teste_a_linha_cabe_e_fala_com_o_leitor_de_tela():
    secao("onda 4b: a linha cabe, e o que a tela diz chega traduzido")
    p = L.PAGINA
    acoes, desc = _linha_cabe(p)
    checar("as Acoes dobram um botao sobre o outro (e nao `nowrap`)", acoes)
    checar("a Descricao tem teto de duas linhas, com o texto inteiro no "
           "`title`", desc and u"esc(s.desc)+'\">'+esc(s.desc)" in p)
    isca = p.replace(u"td.acoes{text-align:right}",
                     u"td.acoes{white-space:nowrap;text-align:right}")
    checar("  (isca) as Acoes em `nowrap` de novo sao acusadas",
           _linha_cabe(isca)[0] is False)
    checar("a Situacao poe o glifo num `<span aria-hidden>` e a frase no seu "
           "no", u"'<span aria-hidden=\"true\">'+glifo+'</span> '" in p
           and u"sit('&#9888;','já tem um RTSTRUCT na pasta')" in p)
    checar("  (isca) a forma de antes, «&#9888; já tem um RTSTRUCT na pasta» "
           "num no so, nao esta mais la",
           u"'&#9888; já tem um RTSTRUCT na pasta'" not in p)
    checar("o «x» de cada tag diz qual estrutura tira (molde)",
           u"'tirar %s do STUDY desta série'.replace('%s', it.nome || it.chave)" in p
           and u'aria-label="tirar do STUDY desta série"' not in p)
    checar("  e o «+» diz qual devolve",
           u"'devolver %s ao STUDY'.replace('%s', it.nome || it.chave)" in p)
    checar("o `?` diz que abre a ajuda, e de que (molde)",
           u"'abrir a ajuda de %s'.replace('%s'" in p
           and u"aria-label=\"' + esc(rotulo) + '\"" not in p)
    checar("a regiao viva diz o que os numeros sao, por `uiTexto`",
           u"'%s estruturas no STUDY, %s fora'.replace('%s', ests.length)" in p
           and u"viva.textContent = ests.length + ' / '" not in p)
    checar("o gancho do fim leva ao «Ver segmentação» e as Reconstrucoes 3D",
           u"Exercite o aprendizado em:" in p
           and u'<a href="/ver">' in p and u'<a href="/recon3d">' in p
           and u"abre nos tr&ecirc;s planos e em 3D" not in p)
    import radai_phrases as F
    tab = dict((F.normalizar(t[0]), t) for t in F.TABELA)
    chaves = (u"já tem um RTSTRUCT na pasta", u"já segmentada",
              u"em processamento", u"parou no meio", u"livre",
              u"tirar %s do STUDY desta série", u"devolver %s ao STUDY",
              u"abrir a ajuda de %s", u"%s estruturas no STUDY, %s fora",
              u"Terminou de processar?", u"Exercite o aprendizado em:")
    sem = [k for k in chaves if not (k in tab and all(tab[k][1:]))]
    checar("e cada frase tem chave nos doze idiomas", not sem, sem)


def teste_substituir_refaz_a_serie_concluida():
    secao(u"o Substituir refaz a serie concluida")
    import inspect
    import json as _j
    import engine as E
    import radai_output as RO
    import radai_records as RG
    import radai_sets as RS
    import radai_queue_state as FQ
    import SimpleITK as sitk

    fora = L._com_escolhas_da_tela({"series": [
        {"uid": "U1", "substituir": True}, {"uid": "U2", "substituir": "sim"},
        {"uid": "U3", "substituir": 1}, {"uid": "U4"}]})
    checar(u"o servidor so aceita o `true` do JSON como «Substituir»",
           fora[0].get("substituir") is True
           and all("substituir" not in d for d in fora[1:]),
           str([d.get("substituir") for d in fora]))
    FQ.limpar()
    try:
        FQ.acrescentar_series([{"uid": "U9", "pasta": "P9", "modo": "auto"}])
        r = FQ.acrescentar_series([{"uid": "U9", "pasta": "P9", "modo": "auto",
                                    "substituir": True}])
        _c = [c for c in FQ.cards() if c.get("uid") == "U9"]
        checar(u"pedir de novo, agora com o «Substituir», atualiza o card que "
               u"espera (e ele entra na carga)",
               r.get("atualizadas") == 1 and _c
               and (_c[0].get("carga") or {}).get("substituir") is True,
               u"%s | %s" % (r, _c[0].get("carga") if _c else None))
    finally:
        FQ.limpar()

    def _fn(pag, nome):
        i = pag.find(u"function %s(" % nome)
        if i < 0:
            return u""
        k, prof = pag.find(u"{", i), 0
        for j in range(k, len(pag)):
            if pag[j] == u"{":
                prof += 1
            elif pag[j] == u"}":
                prof -= 1
                if prof == 0:
                    return pag[i:j + 1]
        return u""
    _campos = re.search(r"(?s)var CAMPOS_DA_ESCOLHA = \[.*?\];", L.PAGINA)
    _dubles = u"""
var CAP = {};
function el(){ return null }
function cartMsg(){} function uiTremer(){} function esc(s){ return s }
function limparSelecao(){}
function escolhaDe(){ return {oar_fora: {}} }
function modoDe(s){ return s.modo || 'auto' }
function _opcDaSerie(){ return false }
function perguntar(o){ CAP.botao = o.ok; o.aoSim() }
function fetch(u, o){ CAP.corpo = JSON.parse(o.body);
  return {then: function(){ return {then: function(){
    return {catch: function(){}} }} }} }
var SEL = [];
function incluidas(){ return SEL }
"""
    _roda = u"""
SEL = [{uid: 'A', situacao: 'concluida', radai_na_pasta: ['x.dcm']},
       {uid: 'B', situacao: 'livre', radai_na_pasta: [], substituir: true}];
rodar();
console.log('JSON:' + JSON.stringify(CAP));
"""
    _fontes = [_fn(L.PAGINA, n) for n in (u"rodar", u"payloadDaSerie",
                                           u"mandarParaAFila", u"_ppsDaSerie",
                                           u"_ppDaSerie", u"_achadosAPedir",
                                           u"_pedirADeclaracao")]
    checar(u"as tres funcoes do pedido estao na pagina",
           all(_fontes) and _campos is not None,
           str([bool(f) for f in _fontes]))
    _js = (_dubles + (_campos.group(0) if _campos else u"") + u"\n"
           + u"\n".join(_fontes) + _roda)
    res, erro = _rodar_js_no_node(_js, prefixo=u"radai_t_subst_js_")
    if erro.startswith(u"PULADO"):
        checar(u"node disponivel para executar o pedido", False, erro)
    else:
        _ser = dict((d.get("uid"), d)
                    for d in ((res or {}).get("corpo") or {}).get("series") or [])
        checar(u"o «Substituir» do dialogo manda a serie concluida com "
               u"`substituir: true`", res is not None
               and res.get("botao") == u"Substituir"
               and (_ser.get("A") or {}).get("substituir") is True,
               erro or str(_ser.get("A")))
        checar(u"  e a serie livre vai sem ele (nem um «substituir» velho "
               u"grudado nela passa)", res is not None and "B" in _ser
               and "substituir" not in _ser["B"], erro or str(_ser.get("B")))
        r2, e2 = _rodar_js_no_node(_js.replace(u"mandarParaAFila(sel, refeitas)",
                                               u"mandarParaAFila(sel)"),
                                   prefixo=u"radai_t_subst_js_")
        _s2 = dict((d.get("uid"), d)
                   for d in ((r2 or {}).get("corpo") or {}).get("series") or [])
        checar(u"  (isca) sem passar as confirmadas, a concluida vai sem o "
               u"«Substituir» -- a checagem discrimina",
               u"mandarParaAFila(sel, refeitas)" in _js and r2 is not None
               and "substituir" not in (_s2.get("A") or {}), e2 or str(_s2))

    base = tempfile.mkdtemp(prefix="radai_t_subst_")
    pasta = os.path.join(base, "PAC", "CT")
    uid = _serie(pasta, 2, 8, 3.0, "B30f", "TC")
    u8 = uid[-8:]
    velho_fast = "RS_RadAI_FAST_20260101_%s.dcm" % u8
    done_velho = {"uid": uid, "machine": "TARDE", "modo": "fast",
                  "finished": "2026-09-27 15:00:00"}
    guardado = {}
    estado = {"levanta": False}

    def _dublar(obj, nome, novo):
        guardado[(id(obj), nome)] = (obj, nome, getattr(obj, nome))
        setattr(obj, nome, novo)

    def _ref():
        img = sitk.Image(8, 8, 8, sitk.sitkInt16)
        img.SetSpacing((0.7, 0.7, 3.0))
        return img

    _alvo_de_verdade = RO.Saida._alvo

    class _Saida(object):
        def __init__(self, engine, stage, destino, rs_name, *a, **k):
            self.destino, self.rs_name = destino, rs_name
            self.gravados = []

        def _alvo(self, infixo):
            return _alvo_de_verdade(self, infixo)

        def full_e_oar(self, *a, **k):
            if estado["levanta"]:
                raise RuntimeError("a cadeia do FULL levantou")
            for c in ("oar", "full"):
                io.open(self._alvo(RS.POR_COD[c]["infixo"]), "wb").write(b"n")
                self.gravados.append(c)
            return {"estruturas": ["Liver_ai"], "oar": "", "full": ""}

        def __getattr__(self, nome):
            return lambda *a, **k: None

    def _radai():
        d = os.path.join(pasta, "_RadAI")
        return sorted(os.listdir(d)) if os.path.isdir(d) else []

    def _preparar():
        for n in os.listdir(pasta):
            if n.startswith("RS_RadAI_"):
                os.remove(os.path.join(pasta, n))
        shutil.rmtree(os.path.join(pasta, "_RadAI"), ignore_errors=True)
        io.open(os.path.join(pasta, velho_fast), "wb").write(b"velho")
        os.makedirs(os.path.join(pasta, "_RadAI"))
        io.open(os.path.join(pasta, "_RadAI", "%s.done.json" % uid), "w",
                encoding="utf-8").write(_j.dumps(done_velho))

    def _rodar(substituir, fn=None, recusa=None, levanta=False, orfao=False):
        _preparar()
        if orfao:
            _d = os.path.join(pasta, "_RadAI", "%s.done.json" % uid)
            os.replace(_d, _d + ".substituido.CAIU.4242")
        estado["levanta"] = levanta
        ev, log = [], []
        s = {"uid": uid, "pasta": pasta, "modalidade": "CT", "pid": "F",
             "curto": u8, "date": "20260101", "modo": "auto"}
        if substituir:
            s["substituir"] = True
        r = (fn or L._uma_serie)(s, False, ["total_v3"], "cpu", None, 60, 60,
                                 log.append, _marcadores_em_disco(ev, recusa),
                                 "BATERIA", 3600, 0.0)
        try:
            done = _j.loads(io.open(os.path.join(
                pasta, "_RadAI", "%s.done.json" % uid),
                encoding="utf-8").read())
        except Exception:
            done = None
        arqs = sorted(n for n in os.listdir(pasta) if n.startswith("RS_RadAI_"))
        return r, ev, log, done, arqs

    velho_cfg = dict(L._CFG)
    try:
        _dublar(E, "copy_sorted", lambda arqs, stage: None)
        _dublar(E, "load_sitk", lambda stage: _ref())
        _dublar(E, "_resolve_device", lambda d: "cpu")
        _dublar(E, "run_ts_task", lambda ref, t, **k: {"liver": 1})
        _dublar(E, "regioes_no_campo",
                lambda masks, grade=None: (("abdome",), []))
        _dublar(RO, "Saida", _Saida)
        _dublar(RG, "registrar_serie", lambda *a, **k: "")
        _dublar(RG, "medir_serie", lambda *a, **k: {})
        L._CFG.clear()
        L._CFG.update({"incluir_nv": 0, "incluir_cads": 0, "incluir_moose": 0})

        r, ev, log, done, arqs = _rodar(False)
        checar(u"sem o «Substituir», a serie concluida e pulada antes do lock",
               r.get("pulo") == "concluida" and "claim" not in ev
               and done == done_velho and arqs == [velho_fast], str(r)[:200])

        r, ev, log, done, arqs = _rodar(True)
        checar(u"com o «Substituir», a serie concluida e REFEITA",
               not r.get("erro") and not r.get("pulada")
               and ("RS_RadAI_FULL_20260101_%s.dcm" % u8) in arqs,
               u"%s | %s" % (r.get("erro") or r.get("pulada"), arqs))
        checar(u"  o `done` anterior saiu ANTES da reserva (a reserva recusa "
               u"serie com `done`)", "reservar:sem_done" in ev, str(ev))
        checar(u"  o `done` novo e o desta execucao (modo AUTO), e o velho "
               u"nao sobra ao lado", (done or {}).get("modo") == "auto"
               and (done or {}).get("machine") == "BATERIA"
               and not any(u"substituido" in n for n in _radai()),
               u"%s | %s" % (done, _radai()))
        checar(u"  e o OAR_Fast da tarde sai: o AUTO nao o grava (a troca de "
               u"modo que a Politica 1.6 descreve)", velho_fast not in arqs,
               str(arqs))
        checar(u"  e o log diz que refez por pedido declarado",
               any(u"«Substituir» foi confirmado" in l for l in log),
               u" | ".join(log[:3]))

        r, ev, log, done, arqs = _rodar(True, levanta=True)
        checar(u"a execucao que falha devolve o `done` anterior, intacto",
               bool(r.get("erro")) and done == done_velho
               and not any(u"substituido" in n for n in _radai()),
               u"%s | %s | %s" % (r.get("erro"), done, _radai()))
        checar(u"  e a entrega anterior fica", velho_fast in arqs, str(arqs))

        r, ev, log, done, arqs = _rodar(
            True, recusa=u"`OUTRA` esta gravando esta serie agora")
        checar(u"a reserva recusada (outra estacao gravando) devolve o `done` "
               u"anterior", r.get("pulo") == "outra" and done == done_velho,
               u"%s | %s" % (r, done))

        r, ev, log, done, arqs = _rodar(False, orfao=True)
        checar(u"com o rastro de um «Substituir» que caiu, o lote o resolve "
               u"ANTES de olhar o `done`: a serie volta a concluida e e pulada",
               ev[:1] == ["resolver"] and "claim" not in ev
               and r.get("pulo") == "concluida" and done == done_velho
               and not any(u"substituido" in n for n in _radai()),
               u"%s | %s | %s" % (ev, r.get("pulo"), _radai()))
        src_e = inspect.getsource(L._uma_serie)
        ns_e = dict(vars(L))
        _cham = u'_resolver_afastado(s["pasta"], s["uid"])'
        exec(compile(src_e.replace(_cham, u"None"), "<isca-orfao>", "exec"),
             ns_e)
        r, ev, log, done, arqs = _rodar(False, orfao=True,
                                        fn=ns_e["_uma_serie"])
        checar(u"  (isca) sem a chamada, a serie concluida seria REFEITA sem "
               u"pedido, e o rastro ficaria -- a checagem discrimina",
               _cham in src_e and "claim" in ev
               and any(u"substituido" in n for n in _radai()),
               u"%s | %s" % (ev, _radai()))

        src = inspect.getsource(L._uma_serie)

        def _isca(velho, novo, nome):
            checar(u"(isca) `%s` esta onde a isca a procura" % velho[:50],
                   src.count(velho) == 1)
            ns = dict(vars(L))
            exec(compile(src.replace(velho, novo), nome, "exec"), ns)
            return ns["_uma_serie"]
        f1 = _isca(u'_substituir = (s.get("substituir") is True)',
                   u'_substituir = False', "<isca-ler>")
        r, ev, log, done, arqs = _rodar(True, fn=f1)
        checar(u"  (isca) sem ler o «Substituir», a serie e pulada -- a "
               u"checagem discrimina", r.get("pulo") == "concluida", str(r)[:120])
        f2 = _isca(u'_subst["lado"] = _afastar_o_done(',
                   u'_subst["lado"] = (lambda *a: None)(', "<isca-afastar>")
        r, ev, log, done, arqs = _rodar(True, fn=f2)
        checar(u"  (isca) sem tirar o `done` antes da reserva, a serie sai "
               u"descartada e nada e refeito -- a checagem discrimina",
               bool(r.get("pulada")) and "reservar:com_done" in ev
               and velho_fast in arqs, u"%s | %s" % (r.get("pulada"), ev))
        f3 = _isca(u'_devolver_o_done(marcadores, s["pasta"], s["uid"], '
                   u'_subst["lado"],',
                   u'(lambda *a: None)(marcadores, s["pasta"], s["uid"], '
                   u'_subst["lado"],', "<isca-devolver>")
        r, ev, log, done, arqs = _rodar(True, fn=f3, levanta=True)
        checar(u"  (isca) sem devolver o `done` na falha, a serie fica sem "
               u"marcador -- a checagem discrimina", done is None, str(done))
    finally:
        for obj, nome, val in guardado.values():
            setattr(obj, nome, val)
        L._CFG.clear()
        L._CFG.update(velho_cfg)
        shutil.rmtree(base, ignore_errors=True)

    FQ.limpar()
    try:
        FQ.acrescentar_series([{"uid": "1.2.3.44445555", "pasta": "PX"}])
        L._fila_diz("concluida", "1.2.3.44445555", pasta="PX")
        _c = FQ.cards()[0]
        _t = FQ.para_tela([_c])[0]
        checar(u"a serie pulada por estar concluida fecha o card como pronto E "
               u"«ja concluida» (a tela diz que nao foi refeita)",
               _c.get("estado") == "pronto" and _c.get("ja_concluida") is True
               and _t.get("ja_concluida") is True, str(_t))
        FQ.acrescentar_series([{"uid": "1.2.3.44445555", "pasta": "PX"}])
        L._fila_diz("feito", "1.2.3.44445555", pasta="PX")
        _cs = [c for c in FQ.cards() if c.get("uid") == "1.2.3.44445555"]
        checar(u"  e a mesma serie refeita depois fecha `pronto` sem a marca",
               len(_cs) == 2 and sum(1 for c in _cs
                                     if c.get("ja_concluida")) == 1
               and all(c.get("estado") == "pronto" for c in _cs), str(_cs))
    finally:
        FQ.limpar()
    corpo = lote_py_txt().split(u"def _rodar_tudo(")[1].split(u"\ndef ")[0]
    checar(u"o lote manda o desfecho «concluida» para a fila como tal (e nao "
           u"como `feito`)",
           re.search(r'get\("pulo"\)\s*==\s*"concluida":\s*(#[^\n]*\s*)*'
                     r'_fila_diz\("concluida"', corpo) is not None)


def teste_a_extracao_do_zip_fica_em_uso_ate_o_lote_acabar():
    secao(u"a extracao do zip fica em uso ate o lote acabar")
    import ast as _ast
    import time as _t
    import radai_archive as A
    raiz = tempfile.mkdtemp(prefix="radai_t_emuso_")
    try:
        serie = os.path.join(raiz, "DICOM", "SE00001")
        os.makedirs(serie)
        io.open(os.path.join(serie, "IM0"), "wb").write(b"x")
        velho = _t.time() - 10 * 3600
        for r_, ds, fs in os.walk(raiz, topdown=False):
            for n in fs + ds:
                os.utime(os.path.join(r_, n), (velho, velho))
        os.utime(raiz, (velho, velho))
        antes = A.pasta_temporaria_em_uso(raiz, 6)[0]
        checar(u"(isca) sem declaracao, a extracao de 10 h SAI -- o caso que "
               u"existia", antes is False, str(antes))
        L._extracao_em_uso(serie)
        em, porque = A.pasta_temporaria_em_uso(raiz, 6)
        checar(u"declarada a serie de dentro, a extracao inteira fica",
               em is True and u"declarada" in porque, porque)
        L.soltar_extracoes_do_lote()
        checar(u"  e soltas as do lote, ela volta a poder sair",
               A.pasta_temporaria_em_uso(raiz, 6)[0] is False)
    finally:
        L.soltar_extracoes_do_lote()
        shutil.rmtree(raiz, ignore_errors=True)

    def _fiacao(fonte):
        arv = _ast.parse(fonte)
        declara = solta = False
        for no in _ast.walk(arv):
            if isinstance(no, _ast.FunctionDef) and no.name == "_uma_serie":
                for se in _ast.walk(no):
                    if (isinstance(se, _ast.If)
                            and "zip" in _ast.dump(se.test)):
                        for c in _ast.walk(se):
                            if (isinstance(c, _ast.Call)
                                    and getattr(c.func, "id", "")
                                    == "_extracao_em_uso"):
                                declara = True
            if isinstance(no, _ast.FunctionDef) and no.name == "_rodar_tudo":
                for t in _ast.walk(no):
                    if isinstance(t, _ast.Try) and t.finalbody:
                        for s_ in t.finalbody:
                            for c in _ast.walk(s_):
                                if (isinstance(c, _ast.Call)
                                        and getattr(c.func, "id", "")
                                        == "soltar_extracoes_do_lote"):
                                    solta = True
        return declara, solta
    fonte = lote_py_txt()
    d, s_ = _fiacao(fonte)
    checar(u"`_uma_serie` declara a extracao no ramo do `.zip`", d)
    checar(u"  e `_rodar_tudo` solta no `finally`", s_)
    d2, s2 = _fiacao(fonte.replace(u"        soltar_extracoes_do_lote()\n",
                                   u""))
    checar(u"  (isca) sem a soltura no `finally`, a leitura acusa",
           d2 and not s2)




def teste_o_lote_extrai_o_zip_pela_conta_do_acervo():
    secao(u"o lote extrai o .zip pela conta do acervo")
    import ast as _ast
    import zipfile as _zf
    import radai_archive as A

    def _uma_conta(fonte):
        for no in _ast.walk(_ast.parse(fonte)):
            if isinstance(no, _ast.FunctionDef) and no.name == "preparar_zip":
                nomes = set()
                for c in _ast.walk(no):
                    if isinstance(c, _ast.Call):
                        nomes.add(getattr(c.func, "attr", None)
                                  or getattr(c.func, "id", None))
                return ("pasta_da_extracao_do_zip" in nomes
                        and "sha1" not in nomes)
        return False
    fonte = lote_py_txt()
    checar(u"`preparar_zip` chama a conta do acervo, e nao tem conta propria",
           _uma_conta(fonte))
    alvo = u"estavel = _arq.pasta_da_extracao_do_zip(caminho) or None"
    velha = (u"marca = hashlib.sha1((\"%s|%d|%d\" % chave).encode("
             u"\"utf-8\")).hexdigest()[:12]; estavel = os.path.join("
             u"tempfile.gettempdir(), \"radai_portal_\" + marca)")
    checar(u"  (isca) com a conta de antes no lugar, a leitura acusa",
           alvo in fonte and not _uma_conta(fonte.replace(alvo, velha)))
    raiz = tempfile.mkdtemp(prefix="radai_t_zipconta_")
    velho_tmp = tempfile.tempdir
    try:
        zp = os.path.join(raiz, "exame.zip")
        with _zf.ZipFile(zp, "w") as z:
            z.writestr("PAC/CT/IM0001", b"x" * 300)
        tempfile.tempdir = os.path.join(raiz, "temp")
        os.makedirs(tempfile.tempdir)
        base, erro = L.preparar_zip(zp)
        checar(u"executando: a pasta do lote e a que o acervo calcula",
               bool(base) and not erro
               and base == A.pasta_da_extracao_do_zip(zp),
               str((os.path.basename(base or u""), erro)))
    finally:
        tempfile.tempdir = velho_tmp
        L._EXTRAIDOS.clear()
        shutil.rmtree(raiz, ignore_errors=True)


def teste_o_selo_do_motor_diz_de_onde_vem():
    secao(u"o selo do motor diz de onde vem a etiqueta")
    import json as _json
    import shutil as _sh
    import subprocess as _sp
    mot = dict((m["cod"], m) for m in L.comparacao_da_tela("CT")
               if m["cod"] != "ts")
    lentos = [c for c, m in mot.items() if m.get("velocidade")]
    checar(u"os motores lentos (CADS e NV) mandam a origem da etiqueta",
           sorted(lentos) == ["cads", "nv"] and all(
               mot[c].get("velocidade_fonte")
               == L.FONTE_DA_VELOCIDADE_DO_MOTOR for c in lentos),
           str(dict((c, mot[c].get("velocidade_fonte")) for c in mot)))
    checar(u"  e o que nao tem etiqueta nao manda origem",
           all(not m.get("velocidade_fonte") for c, m in mot.items()
               if not m.get("velocidade")), str(sorted(mot)))
    node = _sh.which("node")
    if not node:
        checar(u"`node` nesta maquina (PULADO: sem ele o JS nao roda aqui)",
               True)
        return
    pag = L._pagina()
    js = (u"function _no(){ return {className:'', title:'', _f:[], _t:'',"
          u" appendChild:function(x){ this._f.push(x); return x },"
          u" get textContent(){ return this._f.length ? this._f.map("
          u"function(x){ return x.textContent }).join('') : this._t },"
          u" set textContent(v){ this._t = v; this._f = [] } } }" + chr(10)
          + u"var document = {createElement: function(){ return _no() },"
          u" createTextNode: function(t){ return {textContent: t} }};"
          + chr(10)
          + _corpo_js(pag, u"_seloVel") + chr(10)
          + u"var m = %s;" % _json.dumps(mot.get("cads") or {}, default=str)
          + chr(10)
          + u"var sm = _seloVel(m);" + chr(10)
          + u"console.log(JSON.stringify({title: sm.title,"
          u" texto: sm.textContent, nos: sm._f.map(function(x){"
          u" return x.textContent })}));")
    tmp = tempfile.mkdtemp(prefix="radai_t_selo_")

    def _no_node(texto):
        arq = os.path.join(tmp, "selo.js")
        io.open(arq, "w", encoding="utf-8").write(texto)
        r = _sp.run([node, arq], capture_output=True, text=True,
                    encoding="utf-8", timeout=60)
        try:
            return _json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            return {"erro": (r.stderr or u"")[-200:]}
    try:
        d = _no_node(js)
        alvo = u"if(!de && t.velocidade_fonte) de = t.velocidade_fonte;"
        di = _no_node(js.replace(alvo, u""))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    checar(u"o selo do CADS diz «declarada lenta no registro do motor»",
           d.get("title") == L.FONTE_DA_VELOCIDADE_DO_MOTOR
           and d.get("texto") == u"~slow", str(d))
    checar(u"  e o `~` e a etiqueta sao nos separados (a etiqueta casa a chave "
           u"«slow»; o `~` fica fora do dicionario)",
           d.get("nos") == [u"~", u"slow"], str(d.get("nos")))
    checar(u"  (isca) sem ler `velocidade_fonte`, ele diria a origem das "
           u"TASKS -- a checagem discrimina",
           alvo in pag and u"forma do modelo" in (di.get("title") or u""),
           str(di))


def teste_a_varredura_nao_sugere_topografia_por_texto():
    secao(u"a varredura nao sugere topografia por texto")
    base = tempfile.mkdtemp(prefix="radai_t_topo_")
    try:
        _serie(os.path.join(base, "CABECA_PESCOCO"), 1, 24, 3.0, "B30f",
               "TC CABECA E PESCOCO")
        vistas = L.varrer(base, min_cortes=20)
        checar(u"a varredura achou a serie", len(vistas) == 1,
               str(len(vistas)))
        s = vistas[0] if vistas else {}
        checar(u"e ela NAO traz sugestao de topografia",
               "topo" not in s and "topo_motivo" not in s,
               str(dict((k, s.get(k)) for k in ("topo", "topo_motivo"))))
        checar(u"  mas continua trazendo o que ja esta na pasta",
               isinstance(s.get("radai_na_pasta"), list),
               str(s.get("radai_na_pasta")))
    finally:
        shutil.rmtree(base, ignore_errors=True)
    saiu = L._com_escolhas_da_tela(
        {"series": [{"uid": "1", "topo": ["cabeca_pescoco"], "estudos": []}],
         "topografias": [["cabeca_pescoco"]]})
    checar(u"o `topo` de uma pagina velha e descartado pelo servidor",
           "topo" not in saiu[0], str(saiu[0]))
    s2 = L._com_escolhas_da_tela({"series": [{"uid": "2",
                                              "tasks_extra": ["teeth"]}],
                                  "modo": "completo"})[0]
    checar(u"a pagina velha: o modo desconhecido e AUTO, e a escolha dos "
           u"estudos sai com o nome em `legado_v82`",
           s2.get("modo") == "auto" and "tasks_extra" not in s2
           and s2.get("legado_v82") == ["tasks_extra"], str(s2))


_ESCOLHA_DA_V81 = ("modo", "tasks_extra", "motores_extra", "topo")


def _chaves_que_a_tela_declara(fonte):
    import ast as _ast
    arv = _ast.parse(fonte)
    fn = None
    for no in _ast.walk(arv):
        if isinstance(no, _ast.FunctionDef) and no.name == "_com_escolhas_da_tela":
            fn = no
            break
    if fn is None:
        return None
    fora = set()
    for no in _ast.walk(fn):
        if isinstance(no, _ast.Assign):
            for alvo in no.targets:
                if (isinstance(alvo, _ast.Subscript)
                        and isinstance(alvo.value, _ast.Name)
                        and alvo.value.id == "d"):
                    k = alvo.slice
                    if isinstance(k, _ast.Constant) and isinstance(k.value, str):
                        fora.add(k.value)
        elif (isinstance(no, _ast.Call) and isinstance(no.func, _ast.Attribute)
              and no.func.attr == "setdefault"
              and isinstance(no.func.value, _ast.Name)
              and no.func.value.id == "d" and no.args
              and isinstance(no.args[0], _ast.Constant)
              and isinstance(no.args[0].value, str)):
            fora.add(no.args[0].value)
    return fora


def teste_pedir_de_novo_leva_os_estudos_junto():
    secao(u"pedir de novo leva a escolha junto (a fila troca a escolha)")
    import radai_queue_state as F
    UID = u"W2C_REPETIDA"

    def _o_que_o_laco_recebe():
        for s in L._series_a_rodar([], True):
            if s.get("uid") == UID:
                return s
        return {}

    def _pedir(**escolha):
        serie = dict({"uid": UID, "pasta": u"p_w2c", "modalidade": u"CT"},
                     **escolha)
        return L.por_na_fila(L._com_escolhas_da_tela({"series": [serie]}))

    def _cenario(escolha_da_fila):
        velho = F._ESCOLHA
        F._ESCOLHA = tuple(escolha_da_fila)
        med = {}
        try:
            F.limpar()
            _pedir()
            r = _pedir(modo=u"perso", protocolos=[u"torax_mama"],
                       tasks={u"lung_nodules": 1})
            s = _o_que_o_laco_recebe()
            med["a_atualizada"] = r.get("atualizadas")
            med["a_modo"] = s.get("modo")
            med["a_torax"] = L.torax_pedido(s)
            try:
                med["a_tasks"] = tuple(L.tasks_iniciais(s)[0])
            except Exception as e:
                med["a_tasks"] = (u"%s: %s" % (type(e).__name__, e),)
            F.limpar()
            _pedir(modo=u"perso", tasks={u"lung_vessels": 1})
            r = _pedir(modo=u"perso", protocolos=[u"torax_mama", u"abdome"],
                       tasks={u"lung_vessels": 1})
            s = _o_que_o_laco_recebe()
            med["b_conta"] = (r.get("atualizadas"), r.get("repetidas"))
            med["b_protocolos"] = tuple(s.get("protocolos") or ())
            F.limpar()
            _pedir(estudos=[u"torax"])
            _pedir(modo=u"auto")
            s = _o_que_o_laco_recebe()
            med["c_legado"] = s.get("legado_v82")
            F.limpar()
            _pedir(modo=u"perso", protocolos=[u"torax_mama"])
            r = _pedir(modo=u"perso", protocolos=[u"torax_mama"],
                       oar_fora=[u"heart"])
            s = _o_que_o_laco_recebe()
            med["d_conta"] = r.get("atualizadas")
            med["d_fora"] = tuple(s.get("oar_fora") or ())
        finally:
            F._ESCOLHA = velho
            F.limpar()
        return med

    def _defeitos(med):
        fora = []
        if not (med.get("a_atualizada") == 1 and med.get("a_modo") == "perso"
                and med.get("a_torax") is True):
            fora.append(u"(a) a escolha nova nao chegou ao laco")
        tasks = med.get("a_tasks") or ()
        if not ("trunk_cavities" in tasks and "lung_nodules" in tasks):
            fora.append(u"(a) o lote rodaria %r, e nao o escolhido" % (tasks,))
        if not (med.get("b_conta") == (1, 0)
                and u"abdome" in med.get("b_protocolos", ())):
            fora.append(u"(b) o protocolo trocado contou como repetida")
        if med.get("c_legado"):
            fora.append(u"(c) a carga ficou com o registro da aba antiga")
        if not (med.get("d_conta") == 1 and med.get("d_fora") == (u"heart",)):
            fora.append(u"(d) o «x» do OAR nao foi trocado")
        return fora

    real = _cenario(F._ESCOLHA)
    d = _defeitos(real)
    checar(u"pedir de novo com outra escolha: a serie que o laco recebe tem a "
           u"escolha nova (a/b/c/d)", not d,
           u"; ".join(d) + u" | _ESCOLHA=%r" % (F._ESCOLHA,))
    _ESCOLHA_DA_V82 = ("modo", "tasks_extra", "motores_extra", "topo",
                       "estudos", "modo_v81")
    isca = _defeitos(_cenario(_ESCOLHA_DA_V82))
    checar(u"  isca: com a `_ESCOLHA` da v8.2 a checagem reprova (os "
           u"protocolos, a aba antiga e o «x»)", len(isca) >= 3,
           u"; ".join(isca))
    fonte = lote_py_txt()
    ch = _chaves_que_a_tela_declara(fonte)
    checar(u"achei, por ast, as chaves que `_com_escolhas_da_tela` escreve "
           u"(ancora: `modo` e `protocolos` entre elas)",
           bool(ch) and {"modo", "protocolos", "oar_fora"} <= set(ch),
           repr(sorted(ch or ())))
    falta = sorted(set(ch or ()) - set(F._ESCOLHA))
    checar(u"toda chave que a tela escreve na serie esta em "
           u"`radai_queue_state._ESCOLHA`", not falta,
           u"faltam %r em _ESCOLHA=%r" % (falta, F._ESCOLHA))
    forjada = fonte.replace(
        u'        d["modo"] = e["modo"]\n',
        u'        d["modo"] = e["modo"]\n        d["escolha_nova"] = 1\n', 1)
    ch2 = _chaves_que_a_tela_declara(forjada) or set()
    checar(u"  isca: uma chave nova escrita pela tela e acusada",
           forjada != fonte and "escolha_nova" in (ch2 - set(F._ESCOLHA)),
           repr(sorted(ch2 - set(F._ESCOLHA))))


def _uma_serie_com_passos(passos, falhar=False, isca=None, run_ts=None,
                          protocolos=(), chaves=None, tasks=("total_v3",),
                          cfg=None, dones=None, fn=None, declarada=True,
                          log=None, modo="perso", meta=None,
                          gravados=None, fora_regiao=None):
    import radai_records as RG
    import radai_output as RO
    import engine as E
    import SimpleITK as sitk
    base = tempfile.mkdtemp(prefix="radai_t_passos_")
    uid = _serie(os.path.join(base, "PAC_PASSOS", "CT"), 2, 8, 3.0, "B30f",
                 "TC")
    casos = []
    guardado = []

    def _dublar(obj, nome, novo):
        guardado.append((obj, nome, getattr(obj, nome)))
        setattr(obj, nome, novo)

    def _ref():
        img = sitk.Image(8, 8, 8, sitk.sitkInt16)
        img.SetSpacing((0.7, 0.7, 3.0))
        return img

    class _Saida(object):
        def __init__(self, *a, **k):
            self.gravados = list(gravados or [])
            self._a = a
            if meta is not None:
                self.meta_do_full = dict(meta)

        def full_e_oar(self, *a, **k):
            if falhar:
                raise RuntimeError(u"conjunto entregue (FULL/OAR) nao saiu: "
                                   u"parou de proposito na bateria")
            _rs_dublado(self, self._a[2], self._a[3],
                        [c for c in (self.gravados or ["oar"])
                         if c in ("oar", "full", "fast")] or ["oar"])
            ent = {"estruturas": ["Liver_ai"], "oar": "", "full": "",
                   "segundos": 42.5, "etapas": [dict(p) for p in passos]}
            if fora_regiao is not None:
                ent["oar_fora_por_regiao"] = dict(fora_regiao)
            return ent

        def __getattr__(self, nome):
            return lambda *a, **k: None

    class _Nada(object):
        def write_text(self, texto=u"", *a, **k):
            if dones is not None:
                dones.append(texto)
            return 0

    marc = {"has_marker": lambda *a, **k: False,
            "claim": lambda *a, **k: True,
            "unclaim": lambda *a, **k: None,
            "renovar": lambda *a, **k: None,
            "m_path": lambda *a, **k: _Nada()}
    velho_cfg = dict(L._CFG)
    try:
        _dublar(E, "copy_sorted", lambda arqs, stage: None)
        _dublar(E, "load_sitk", lambda stage: _ref())
        _dublar(E, "_resolve_device", lambda d: "cpu")
        _dublar(E, "run_ts_task",
                run_ts or (lambda ref, t, **k: {"liver": 1}))
        _dublar(E, "regioes_no_campo",
                lambda masks, grade=None: (("abdome",), []))
        _dublar(RO, "Saida", _Saida)
        _dublar(RG, "registrar_serie",
                lambda *a, **k: casos.append(dict(k)) or "")
        if isca == "sem_etapas_do_caso":
            _dublar(RO, "etapas_do_caso",
                    lambda etapas, p, segundos=None: [
                        dict(e) for e in (etapas or ())])
        L._CFG.clear()
        L._CFG.update(cfg or {})
        _s = {"uid": uid, "pasta": os.path.join(base, "PAC_PASSOS", "CT"),
              "modalidade": "CT", "pid": "F", "curto": "c"}
        if declarada:
            _s.update({"modo": modo, "protocolos": list(protocolos),
                       "tasks": dict(chaves or {})})
            series = L._com_escolhas_da_tela({"series": [_s]})
        else:
            series = [_s]
        res = (fn or L._uma_serie)(series[0], False, list(tasks), "cpu", None,
                                   60, 60,
                                   (log.append if log is not None else None),
                                   marc, "BATERIA", 3600, 0.0)
    finally:
        for obj, nome, val in reversed(guardado):
            setattr(obj, nome, val)
        L._CFG.clear()
        L._CFG.update(velho_cfg)
        shutil.rmtree(base, ignore_errors=True)
    return res, (casos[0] if casos else {})


def teste_os_passos_do_full_chegam_ao_caso_do_lote():
    secao(u"os passos da cadeia do FULL chegam ao caso do lote (F3)")
    import radai_output as RO
    passos = [{"etapa": u"pele e parede", "segundos": 1.5,
               RO.PARTE_DE: RO.PAI_DOS_PASSOS},
              {"etapa": u"montagem e gravacao do FULL", "segundos": 38.0,
               RO.PARTE_DE: RO.PAI_DOS_PASSOS},
              {"etapa": u"FULL: suavizacao (duas passadas) e compostos",
               "segundos": 20.1,
               RO.PARTE_DE: u"montagem e gravacao do FULL"}]
    res, caso = _uma_serie_com_passos(passos)
    _todas = list(caso.get("etapas") or [])
    checar(u"o caso comeca pelas tasks de inferencia («TS <task>»)",
           _todas and str(_todas[0].get("etapa", u"")).startswith(u"TS "),
           [e.get("etapa") for e in _todas[:2]])
    et = [e for e in _todas if not str(e.get("etapa", u"")).startswith(u"TS ")]
    nomes = [e.get("etapa") for e in et]
    checar(u"a serie foi ate o fim e o caso foi registrado",
           not res.get("erro") and bool(caso), str(res.get("erro"))[:120])
    checar(u"o caso tem a linha «FULL e OAR» com o tempo da cadeia (42,5 s)",
           et and et[0] == {"etapa": RO.PAI_DOS_PASSOS, "segundos": 42.5},
           str(et[:1]))
    checar(u"  e os %d passos logo depois dela, com `parte_de`" % len(passos),
           et[1:1 + len(passos)] == passos, nomes)
    checar(u"  e a «serie inteira» no fim",
           nomes and nomes[-1] == "serie inteira"
           and len(et) == len(passos) + 2, nomes)

    res_f, caso_f = _uma_serie_com_passos(passos, falhar=True)
    nomes_f = [e.get("etapa") for e in (caso_f.get("etapas") or [])
               if not str(e.get("etapa", u"")).startswith(u"TS ")]
    checar(u"a cadeia que FALHA: a serie diz o erro, e o caso sai mesmo assim",
           bool(res_f.get("erro")) and bool(caso_f), str(res_f.get("erro"))[:120])
    checar(u"  so com a «serie inteira»: nenhum passo, nenhum pai inventado",
           nomes_f == ["serie inteira"], nomes_f)

    res_i, caso_i = _uma_serie_com_passos(passos, isca="sem_etapas_do_caso")
    et_i = list(caso_i.get("etapas") or [])
    checar(u"ISCA: sem `etapas_do_caso`, o caso sai sem passo nenhum (o "
           u"defeito da revisao, reproduzido)",
           bool(caso_i) and not any(RO.e_passo(e) for e in et_i),
           [e.get("etapa") for e in et_i])


def teste_o_corte_do_detalhe_do_zip():
    secao(u"o corte do detalhe do .zip, que o log do visor usa")
    import ast as _ast
    import inspect as _insp
    import radai_viewseg as _vs
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from fastapi import FastAPI
    app = FastAPI()
    L.montar(app, {"tasks": ["total_v3"], "device": "cpu"})
    vivas = set((m, getattr(r, "path", u"")) for r in app.routes
                for m in (getattr(r, "methods", None) or ()))
    checar(u"o estado do lote e o cancelar dele nao tem mais rota (a barra "
           u"usa a fila e o pipeline)",
           ("GET", u"/api/lote/estado") not in vivas
           and ("POST", u"/api/lote/cancelar") not in vivas
           and not hasattr(L, "estado_sem_phi"),
           str(sorted(p for m, p in vivas if p.startswith(u"/api/lote"))))
    checar(u"  e o cancelar de verdade continua, pelo pipeline",
           ("POST", u"/api/pipeline/cancelar") in vivas
           and callable(getattr(L, "cancelar", None)))
    membro = (u"RuntimeError: N\u00e3o consegui extrair: File "
              u"'VIZINHO FANTOMA/CT/IM0001.dcm' is encrypted")

    def _corta_o_membro(f):
        t = f(membro)
        return (u"consegui extrair" in t and u"VIZINHO FANTOMA" not in t
                and L.DETALHE_DO_ZIP_OMITIDO in t)
    checar(u"a frase da extracao fica, e o membro do .zip sai",
           _corta_o_membro(L.sem_detalhe_do_zip), L.sem_detalhe_do_zip(membro))
    de_zip = L.sem_detalhe_do_zip(u"BadZipFile: OUTRO FANTOMA/CT/x.dcm",
                                  de_zip=True)
    checar(u"  e o erro de um .zip perde o detalhe inteiro depois da classe",
           de_zip.startswith(u"BadZipFile: ") and u"OUTRO FANTOMA" not in de_zip,
           de_zip)
    checar(u"  e o texto que nao fala de .zip passa intacto",
           L.sem_detalhe_do_zip(u"RuntimeError: sem cortes")
           == u"RuntimeError: sem cortes")
    checar(u"ISCA: sem o corte, o membro de outra pasta fica no texto (a "
           u"checagem sabe reprovar)",
           not _corta_o_membro(lambda t, de_zip=False: t))
    _arv = _ast.parse(_insp.getsource(_vs._erro_da_serie_para_o_log))
    _chama = [n for n in _ast.walk(_arv) if isinstance(n, _ast.Call)
              and isinstance(n.func, _ast.Attribute)
              and n.func.attr == "sem_detalhe_do_zip"]
    checar(u"a regra do corte e UMA SO: o log do visor "
           u"(`radai_viewseg._erro_da_serie_para_o_log`) chama a do lote",
           len(_chama) == 1)


def teste_a_task_marcada_que_falha_nao_derruba_a_serie():
    secao(u"a task marcada que falha nao derruba a serie no Rodar agora")
    import ast
    import inspect
    import json

    def _run(ref, t, **k):
        if t == "breasts":
            raise MemoryError("not enough memory: 12907446880 bytes")
        return dict(("%s_%d" % (t, i), 1) for i in range(5))
    cfg = {"classificar_erro": (lambda e: "recurso"
                                if isinstance(e, MemoryError)
                                else "deterministico"),
           "erro_de_ambiente": lambda m: "no module named" in str(m).lower(),
           "limpar_erro": lambda m: str(m).strip()}
    dones = []
    linhas = []
    res, caso = _uma_serie_com_passos([], run_ts=_run, protocolos=["torax_mama"],
                                       cfg=cfg,
                                      dones=dones, log=linhas)
    checar(u"a serie sai: sem erro, e o OAR contado (o FULL e o OAR rodaram)",
           not res.get("erro") and res.get("estruturas") == 1,
           u"%s | estruturas=%s" % (res.get("erro"), res.get("estruturas")))
    tf = res.get("tasks_falharam") or []
    checar(u"a task que falhou vai para `tasks_falharam`, com a CLASSE que o "
           u"vigia injeta", len(tf) == 1
           and tf[0].get("task") == "breasts"
           and tf[0].get("classe") == "recurso"
           and "MemoryError" in (tf[0].get("erro") or ""), str(tf))
    done = json.loads(dones[-1]) if dones else {}
    checar(u"o `done` diz o que rodou e o que nao saiu",
           "breasts" not in (done.get("tasks_ok") or [])
           and "trunk_cavities" in (done.get("tasks_ok") or [])
           and [f.get("task") for f in done.get("tasks_falharam") or []]
           == ["breasts"], str(done)[:300])
    et = [e for e in (caso.get("etapas") or [])
          if str(e.get("etapa", u"")).startswith(u"TS ")]
    nomes = [e.get("etapa") for e in et]
    checar(u"o caso tem uma etapa «TS <task>» por task (a base e as tres "
           u"do protocolo, o derrame incluido)", len(et) == 4
           and u"TS trunk_cavities" in nomes
           and u"TS breasts" in nomes, nomes)
    chaves = set(["etapa", "task", "segundos", "maquina", "dispositivo"])
    checar(u"  cada uma com tempo, maquina e dispositivo (spec E3/F3)",
           bool(et) and all(set(e) - set(["falhou"]) == chaves
                            and e.get("maquina") and e.get("dispositivo")
                            for e in et), str(et[:1]))
    checar(u"  e a que falhou diz que falhou",
           [e.get("task") for e in et if e.get("falhou")]
           == ["breasts"], nomes)
    ex = caso.get("execucao") or {}
    checar(u"`tasks_rodadas` sai preenchido (era nulo), sem a que falhou",
           bool(ex.get("tasks_rodadas")) and "breasts"
           not in ex["tasks_rodadas"] and "trunk_cavities" in ex["tasks_rodadas"],
           str(ex.get("tasks_rodadas")))
    se = caso.get("serie") or {}
    checar(u"a serie do caso tem a espessura e as medidas da imagem",
           se.get("espessura_mm") == 3.0 and se.get("forma_zyx") == [8, 8, 8]
           and se.get("fov_mm") == 5.6, str(se))

    for arq in ("radai_batch.py", "radai_watcher.py"):
        arv = ast.parse(io.open(_componentes.fonte("app/" + arq),
                                encoding="utf-8").read())
        mao = [n for n in ast.walk(arv) if isinstance(n, ast.Dict)
               and any(isinstance(k, ast.Constant) and k.value == "etapa"
                       for k in n.keys)
               and any(isinstance(v, ast.BinOp)
                       and isinstance(v.left, ast.Constant)
                       and str(v.left.value).startswith("TS ")
                       for v in n.values)]
        chama = [n for n in ast.walk(arv) if isinstance(n, ast.Call)
                 and (getattr(n.func, "attr", None)
                      or getattr(n.func, "id", None)) == "etapa_da_task"]
        checar(u"%s monta a linha «TS <task>» por `etapa_da_task`, e nao a "
               u"mao" % arq, bool(chama) and not mao,
               u"%d chamada(s), %d a mao" % (len(chama), len(mao)))

    res_l, _c = _uma_serie_com_passos(
        [], run_ts=_run, cfg=cfg, declarada=False,
        tasks=("total_v3", "breasts"))
    checar(u"ISCA: a lista do CHAMADOR (sem `estudos`) continua sob o C5 — "
           u"a task que falha derruba a serie",
           "MemoryError" in (res_l.get("erro") or u""),
           str(res_l.get("erro"))[:120])

    class Cancelado(RuntimeError):
        pass

    def _run_c(ref, t, **k):
        if t == "breasts":
            raise Cancelado("interrompido")
        return {"liver": 1}
    res_c, _c = _uma_serie_com_passos([], run_ts=_run_c, protocolos=["torax_mama"],
                                       cfg=cfg)
    checar(u"ISCA: o cancelamento no meio de uma task marcada SOBE (a serie "
           u"e interrompida, e nao entregue)",
           bool(res_c.get("cancelado")) and not res_c.get("rs"),
           str(res_c)[:160])

    checar(u"`estruturas` e o numero do OAR nas duas pontas (a serie e o "
           u"caso), e nao o das mascaras da inferencia",
           res.get("estruturas") == 1
           and (caso.get("resultado") or {}).get("estruturas") == 1,
           u"res=%s caso=%s" % (res.get("estruturas"),
                                (caso.get("resultado") or {}).get(
                                    "estruturas")))
    checar(u"as tasks do caso (`versoes.tasks`, «as realmente usadas») nao "
           u"tem a que falhou", "breasts" not in
           list(caso.get("tasks") or ())
           and "trunk_cavities" in list(caso.get("tasks") or ()),
           str(caso.get("tasks")))
    checar(u"o log diz «mascara(s) da inferencia», e nao «apos o nosso "
           u"pos-processamento» (que ainda nao rodou)",
           any(u"mascara(s) da inferencia" in l for l in linhas)
           and not any(u"apos o nosso pos-processamento" in l
                       for l in linhas), [l for l in linhas
                                          if u"mascara" in l][:2])

    def _com(de, para, nome):
        src_ = inspect.getsource(L._uma_serie)
        ns_ = dict(vars(L))
        exec(compile(src_.replace(de, para), nome, "exec"), ns_)
        return de in src_, ns_["_uma_serie"]
    achou, f4 = _com(u'res["estruturas"] = len(nomes)',
                     u'res["estruturas"] = len(masks)', "<isca-estruturas>")
    res4, caso4 = _uma_serie_com_passos([], run_ts=_run, protocolos=["torax_mama"],
                                         cfg=cfg, fn=f4)
    checar(u"ISCA: com `len(masks)` de volta, a serie conta as 15 mascaras da "
           u"inferencia e a checagem de cima reprova",
           achou and res4.get("estruturas") == 15
           and (caso4.get("resultado") or {}).get("estruturas") == 15,
           u"achou=%s res=%s" % (achou, res4.get("estruturas")))
    achou, f5 = _com(u"tasks=tuple(_tasks_ok or tasks or ())",
                     u"tasks=tuple(tasks or ())", "<isca-tasks>")
    _r5, caso5 = _uma_serie_com_passos([], run_ts=_run, protocolos=["torax_mama"],
                                        cfg=cfg, fn=f5)
    checar(u"ISCA: com a lista pedida de volta, a task que falhou reaparece "
           u"nas tasks do caso", achou and "breasts"
           in list(caso5.get("tasks") or ()), str(caso5.get("tasks")))
    achou, f6 = _com(u'"%d mascara(s) da inferencia (do modelo, antes do "',
                     u'"%d estrutura(s) apos o nosso pos-processamento '
                     u'geometrico (" ', "<isca-frase>")
    linhas6 = []
    _uma_serie_com_passos([], run_ts=_run, protocolos=["torax_mama"],
                           cfg=cfg, fn=f6, log=linhas6)
    checar(u"ISCA: com a frase velha, o log volta a dizer «apos o nosso "
           u"pos-processamento» (a checagem sabe reprovar)",
           achou and any(u"apos o nosso pos-processamento" in l
                         for l in linhas6), achou)

    def _run_amb(ref, t, **k):
        if t == "breasts":
            raise ModuleNotFoundError("No module named 'torch'")
        return {"liver": 1}
    res_a, _c = _uma_serie_com_passos([], run_ts=_run_amb, protocolos=["torax_mama"],
                                       cfg=cfg)
    checar(u"o erro de AMBIENTE numa task marcada derruba a serie (a estacao "
           u"nao tem o que rodar; seguir com a base esconderia isso)",
           "torch" in (res_a.get("erro") or u"") and not res_a.get("rs"),
           str(res_a.get("erro"))[:120])
    _velha = L._task_marcada_pode_falhar
    try:
        L._task_marcada_pode_falhar = (
            lambda e: type(e).__name__ != "Cancelado")
        res_ai, _c = _uma_serie_com_passos([], run_ts=_run_amb,
                                           protocolos=["torax_mama"],
                                            cfg=cfg)
    finally:
        L._task_marcada_pode_falhar = _velha
    checar(u"ISCA: com a regra ignorando o ambiente, a serie segue com a "
           u"task em `tasks_falharam` (a checagem sabe reprovar)",
           not res_ai.get("erro") and [
               f.get("task") for f in res_ai.get("tasks_falharam") or []]
           == ["breasts"], str(res_ai)[:160])

    src = inspect.getsource(L._uma_serie)
    alvo = (u"            if not _task_marcada_pode_falhar(e_t):\n"
            u"                return True\n")
    checar(u"  (isca) a tolerancia esta onde a isca a procura", alvo in src)
    ns = dict(vars(L))
    exec(compile(src.replace(alvo, u"            return True\n"),
                 "<isca-tolerancia>", "exec"), ns)
    res_i, _c = _uma_serie_com_passos([], run_ts=_run, protocolos=["torax_mama"],
                                       cfg=cfg,
                                      fn=ns["_uma_serie"])
    checar(u"ISCA: sem a tolerancia, a MemoryError da task marcada derruba a "
           u"serie (o defeito da revisao, reproduzido)",
           "MemoryError" in (res_i.get("erro") or u"")
           and not res_i.get("estruturas"), str(res_i.get("erro"))[:120])



_ZF = 30
_CAIXAS_DA_BASE = (
    ("lung_upper_lobe_left", (14, 28, 40, 80, 70, 95)),
    ("lung_lower_lobe_left", (6, 14, 40, 80, 70, 95)),
    ("lung_upper_lobe_right", (16, 28, 40, 80, 30, 55)),
    ("lung_middle_lobe_right", (11, 16, 40, 80, 30, 55)),
    ("lung_lower_lobe_right", (6, 11, 40, 80, 30, 55)),
    ("heart", (8, 16, 45, 65, 57, 69)),
    ("aorta", (4, 26, 70, 76, 60, 66)),
    ("trachea", (18, 28, 60, 64, 61, 65)),
    ("esophagus", (4, 28, 78, 82, 61, 64)),
    ("small_bowel", (0, 5, 40, 60, 40, 80)),
    ("kidney_left", (0, 6, 80, 95, 80, 95)),
    ("colon", (0, 4, 62, 72, 44, 60)),
    ("atrial_appendage_left", (14, 16, 45, 48, 69, 71)),
)


def _cruas_do_fantoma(t):
    import numpy as np
    import engine as E
    import radai_tasks as _rt
    lab = np.zeros((_ZF, 128, 128), np.int16)
    if _rt.familia_da_task(t) == "total":
        idx = {}
        for i, (nome, (z0, z1, y0, y1, x0, x1)) in enumerate(_CAIXAS_DA_BASE,
                                                             start=1):
            lab[z0:z1, y0:y1, x0:x1] = i
            idx[i] = nome
        return E.MasksCruas(lab, idx)
    if t == "trunk_cavities":
        lab[0:5, 30:40, 30:40] = 1
        lab[20:24, 50:60, 20:30] = 2
        lab[20:24, 50:60, 100:110] = 3
        lab[9:15, 43:67, 55:71] = 4
        return E.MasksCruas(lab, {1: "abdominal_cavity", 2: "mediastinum",
                                  3: "thoracic_cavity", 4: "pericardium"})
    if t == "breasts":
        lab[12:20, 30:40, 20:40] = 1
        lab[12:20, 30:40, 88:108] = 1
        return E.MasksCruas(lab, {1: "breast"})
    if t == "lung_vessels":
        lab[14:20, 50:60, 75:85] = 1
        return E.MasksCruas(lab, {1: "lung_vessels"})
    return None


def _rodar_no_fantoma(serie_escolha, base, nome, regioes=("torax",),
                      fn=None):
    import engine as E
    import radai_topography as TP
    from datetime import datetime as _dt
    sys.path.insert(0, AQUI)
    from make_test_series import escreve_serie
    pasta = os.path.join(base, nome)
    uid = escreve_serie(pasta, "PAC_PREVIA", _dt(2026, 9, 27), _ZF)
    s = dict({"uid": uid, "pasta": pasta, "modalidade": "CT",
              "pid": "PAC_PREVIA", "curto": uid[-8:], "date": "20260927"},
             **serie_escolha)
    s = L._com_escolhas_da_tela({"series": [s]})[0]
    dub = []

    def _ts(ref, t, **k):
        c = _cruas_do_fantoma(t)
        if c is not None and k.get("cruas") is not None:
            k["cruas"][t] = c
        return {"liver_%s" % t: 1}

    class _Nada(object):
        def write_text(self, *a, **k):
            return 0
    marc = {"has_marker": lambda *a, **k: False,
            "claim": lambda *a, **k: True,
            "unclaim": lambda *a, **k: None,
            "renovar": lambda *a, **k: None,
            "m_path": lambda *a, **k: _Nada()}
    velho = dict(L._CFG)
    try:
        for obj, n, novo in ((E, "run_ts_task", _ts),
                             (TP, "anatomia_da_base",
                              lambda m, g, cruas=None, motor=None: {
                                  "regioes": tuple(regioes),
                                  "laudo": [u"dublada"],
                                  "coracao_cm3": None,
                                  "pescoco": (False, u"pescoco: nao")})):
            dub.append((obj, n, getattr(obj, n)))
            setattr(obj, n, novo)
        L._CFG.clear()
        res = (fn or L._uma_serie)(s, False, ["total_v3"], "cpu", None, 600,
                                   600, None, marc, "BATERIA", 3600, 1.5)
    finally:
        for obj, n, v in reversed(dub):
            setattr(obj, n, v)
        L._CFG.clear()
        L._CFG.update(velho)
    return res, pasta, s


def _rois_do_arquivo(caminho):
    import pydicom
    try:
        ds = pydicom.dcmread(caminho, force=True)
        return set(str(x.ROIName) for x in ds.StructureSetROISequence)
    except Exception:
        return set()


def teste_a_parotida_do_viii_e_uma_linha_so_na_previa():
    secao(u"a parotida do VIII e uma linha so na previa, e o x vale para as "
          u"duas chaves")
    import radai_sets as RS
    tasks = ["total_v3", "head_glands_cavities", "headneck_muscles",
             "headneck_bones_vessels", L.CHAVE_DOS_NIVEIS]

    def _par(lista, nome):
        return [e for e in lista if e["nome"] == nome]

    ests, fora = L.estruturas_do_oar_possiveis("perso", tasks, "CT")
    pl = _par(ests, u"Parotid_L_ai")
    checar(u"a Parotid_L_ai aparece uma vez, com a chave do nivel VIII",
           len(pl) == 1 and pl[0]["chave"] == "parotid_lnl_left", str(pl))
    checar(u"  e a Parotid_R_ai tambem", [e["chave"] for e in _par(
        ests, u"Parotid_R_ai")] == ["parotid_lnl_right"])
    for x in ("parotid_lnl_left", "parotid_gland_left", "Parotid_L_ai"):
        e2, f2 = L.estruturas_do_oar_possiveis("perso", tasks, "CT",
                                               oar_fora=[x])
        checar(u"o x em %s tira a Parotid_L_ai da previa, uma vez, e a "
               u"direita fica" % x,
               not _par(e2, u"Parotid_L_ai")
               and len(_par(f2, u"Parotid_L_ai")) == 1
               and len(_par(e2, u"Parotid_R_ai")) == 1,
               u"ests=%s fora=%s" % (_par(e2, u"Parotid_L_ai"),
                                     _par(f2, u"Parotid_L_ai")))
    sem = [t for t in tasks if t != L.CHAVE_DOS_NIVEIS]
    e3, _f3 = L.estruturas_do_oar_possiveis("perso", sem, "CT")
    checar(u"sem os niveis, nenhuma parotida na previa do OAR (a do "
           u"TotalSegmentator fica so no FULL)",
           not _par(e3, u"Parotid_L_ai") and not _par(e3, u"Parotid_R_ai"),
           str(_par(e3, u"Parotid_L_ai")))
    velho = RS.PERMITIDOS_NO_OAR
    try:
        RS.PERMITIDOS_NO_OAR = frozenset(
            set(velho) | {"parotid_gland_left", "parotid_gland_right"})
        e4, _f4 = L.estruturas_do_oar_possiveis("perso", sem, "CT")
    finally:
        RS.PERMITIDOS_NO_OAR = velho
    checar(u"ISCA: com a do TotalSegmentator de volta na lista do OAR, a "
           u"previa sem os niveis mostraria a Parotid_L_ai",
           len(_par(e4, u"Parotid_L_ai")) == 1)


def teste_a_previa_bate_com_o_que_a_execucao_grava():
    secao(u"a previa da entrega bate com o que a execucao grava")
    import engine as E
    import radai_sets as RS
    import radai_tasks as _RT
    _todas = dict((d["task"], 1) for d in _RT.CATALOGO
                  if str(d.get("modalidade")) == "CT")
    _todas.update((c, 1) for c in L.CHAVES_DOS_MOTORES_DO_FULL)
    _todas[L.CHAVE_DOS_NIVEIS] = 1
    _max = L.previa_da_entrega(L._com_escolhas_da_tela({"series": [
        {"uid": "9.9.9.9.9.9", "modo": "perso",
         "protocolos": ["torax_mama"], "tasks": _todas}]})[0])
    _ch = set(e["chave"] for e in _max["oar"]["estruturas"])
    # GUARDA: a chave substituida sai pela linha da que a substitui.
    _ch |= set(v for k, v in RS.MESMA_ROI_NO_OAR.items() if k in _ch)
    _licenciada = set(k for k, f in E.TS_MAP.items()
                      if set(f or {}) == {"brain_structures"})
    _sem = sorted(set(RS.PERMITIDOS_NO_OAR) - _ch - _licenciada)
    checar(u"toda chave do OAR tem de onde sair (menos a task licenciada)",
           not _sem, str(_sem))
    base = tempfile.mkdtemp(prefix="radai_t_previa_")
    try:
        casos = (
            ("perso", {"modo": "perso", "protocolos": ["torax_mama"],
                       "tasks": {"abdominal_muscles": 0, "lung_vessels": 1},
                       "comparacao": {"ts": 1}, "oar_fora": ["esophagus"]}),
            ("fast", {"modo": "fast"}),
            ("auto", {"modo": "auto"}),
        )
        vistos = {}
        for nome, esc in casos:
            res, pasta, s = _rodar_no_fantoma(esc, base, nome)
            prev = L.previa_da_entrega(s)
            gravados = sorted(f for f in os.listdir(pasta)
                              if f.startswith("RS_RadAI_"))
            vistos[nome] = (res, pasta, s, prev, gravados)
            checar(u"[%s] a serie foi ate o fim sem erro" % nome,
                   not res.get("erro"), str(res.get("erro"))[:200])
            checar(u"[%s] os arquivos que a previa anuncia sao os que a "
                   u"execucao grava" % nome,
                   sorted(a["arquivo"] for a in prev["arquivos"]) == gravados,
                   u"previa=%s | disco=%s" % (
                       sorted(a["arquivo"] for a in prev["arquivos"]),
                       gravados))
            ent = [a for a in prev["arquivos"] if a.get("entregue")]
            rois = _rois_do_arquivo(os.path.join(pasta, ent[0]["arquivo"])) \
                if ent else set()
            nomes = set(e["nome"] for e in prev["oar"]["estruturas"])
            checar(u"[%s] toda ROI do entregue foi anunciada pela previa"
                   % nome, bool(rois) and rois <= nomes,
                   str(sorted(rois - nomes)))
        _r, pasta_p, _s, prev_p, _g = vistos["perso"]
        _ent = [a for a in prev_p["arquivos"] if a.get("entregue")][0]
        rois_p = _rois_do_arquivo(os.path.join(pasta_p, _ent["arquivo"]))
        nomes_p = set(e["nome"] for e in prev_p["oar"]["estruturas"])
        checar(u"[perso] sem a `abdominal_muscles`, a Breast_OAR nao esta na "
               u"previa nem no OAR gravado",
               not any(n.startswith(u"Breast_OAR") for n in nomes_p | rois_p),
               str(sorted(n for n in nomes_p | rois_p if u"Breast" in n)))
        checar(u"[perso] e a glandula (da `breasts`) esta nas duas pontas",
               any(n.startswith(u"Breast_L") for n in nomes_p),
               str(sorted(n for n in nomes_p if u"Breast" in n)))
        _fora = set(e["chave"] for e in prev_p["oar"]["fora"])
        _full = [a for a in prev_p["arquivos"] if a["cod"] == "full"][0]
        rois_full = _rois_do_arquivo(os.path.join(pasta_p, _full["arquivo"]))
        checar(u"[perso] o «x» tira o esofago do OAR nas duas pontas, e ele "
               u"fica no FULL",
               _fora == {"esophagus"} and u"Esophagus_ai" not in rois_p
               and u"Esophagus_ai" not in nomes_p
               and u"Esophagus_ai" in rois_full,
               u"fora=%s oar=%s full=%s" % (_fora, u"Esophagus_ai" in rois_p,
                                            u"Esophagus_ai" in rois_full))
        _r, pasta_f, _s, prev_f, grav_f = vistos["fast"]
        nomes_f = set(e["nome"] for e in prev_f["oar"]["estruturas"])
        rois_f = _rois_do_arquivo(os.path.join(pasta_f, grav_f[0])) \
            if grav_f else set()
        checar(u"[fast] so o RadAI_STUDY_Fast, e sem Bag_Bowel nas duas pontas",
               len(grav_f) == 1 and grav_f[0].startswith(u"RS_RadAI_FAST_")
               and u"Bag_Bowel_ai" not in nomes_f
               and u"Bag_Bowel_ai" not in rois_f, str(grav_f))
        _r, pasta_a, _s, prev_a, grav_a = vistos["auto"]
        checar(u"[auto] o FULL e o OAR, e SEM o TS cru (spec 1.1)",
               not any(u"_TS_" in g for g in grav_a) and len(grav_a) == 2,
               str(grav_a))
        _com = L.previa_da_entrega(L._com_escolhas_da_tela({"series": [
            {"uid": "1.2.3.4.5.6", "modo": "perso",
             "protocolos": ["torax_mama"],
             "tasks": {"abdominal_muscles": 1}}]})[0])
        _nomes_com = set(e["nome"] for e in _com["oar"]["estruturas"])
        checar(u"a Breast_OAR saiu: nem com a mama e os musculos a previa a "
               u"anuncia", not any(n.startswith(u"Breast_OAR")
                                   for n in _nomes_com),
               str(sorted(n for n in _nomes_com if u"Breast" in n)))
        checar(u"  e as exigencias da previa nao citam mais a Breast_OAR",
               not any(k.startswith("breast_oar")
                       for k in L.EXIGENCIAS_NA_PREVIA))
        _chaves_com = set(e["chave"] for e in _com["oar"]["estruturas"])
        checar(u"a Bag_Bowel_OAR esta na previa do OAR, e a Bag_Bowel nao "
               u"(ela e so do FULL)", "bag_bowel_oar" in _chaves_com
               and "bag_bowel" not in _chaves_com, str(sorted(_chaves_com)))
        _fast = L.previa_da_entrega(L._com_escolhas_da_tela({"series": [
            {"uid": "1.2.3.4.5.6", "modo": "fast"}]})[0])
        _chaves_fast = set(e["chave"] for e in _fast["oar"]["estruturas"])
        checar(u"  e o FAST nao anuncia bag nenhuma",
               not any(k.startswith("bag_bowel") for k in _chaves_fast),
               str(sorted(_chaves_fast)))
        try:
            import json as _json
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from fastapi import FastAPI
                from fastapi.testclient import TestClient
            app = FastAPI()
            L.montar(app, {"device": "cpu"})
            s_p = dict(vistos["perso"][2])
            r = TestClient(app).post("/api/lote/previa_da_entrega",
                                     json={"serie": s_p})
            d = r.json() if r.status_code == 200 else {}
            checar(u"/api/lote/previa_da_entrega responde a mesma previa",
                   [a["arquivo"] for a in d.get("arquivos") or ()]
                   == [a["arquivo"] for a in prev_p["arquivos"]],
                   str(d)[:200])
            corpo = r.text
            checar(u"  e o corpo nao leva a pasta nem o UID inteiro",
                   s_p["pasta"].replace("\\", "\\\\") not in corpo
                   and s_p["pasta"] not in corpo and s_p["uid"] not in corpo,
                   corpo[:120])
            r2 = TestClient(app).post("/api/lote/previa_da_entrega", json={
                "serie": dict(s_p, protocolos=["torax_mama"], modo="perso")})
            checar(u"  e aceita a serie direto no corpo, ou dentro de `serie`",
                   r2.status_code == 200 and not (r2.json() or {}).get("erro"))
        except ImportError as e:
            checar(u"a rota responde (fastapi ausente)", True, str(e))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_a_task_travada_vai_para_o_fim():
    secao(u"a task travada vai para o fim, e a trava chega ao motor")
    import engine as E
    ordem, kw_vistos = [], {}
    estado = {"trava": {"breasts": 2}}

    def _run(ref, t, **k):
        ordem.append((t, bool(k.get("plano_menor"))))
        kw_vistos.setdefault(t, []).append(k.get("trava"))
        n = estado["trava"].get(t, 0)
        if n:
            estado["trava"][t] = n - 1
            raise E.TaskTravada(t, "sem_pulso", {"sem_pulso_s": 900.0,
                                                 "limite_s": 900.0,
                                                 "pulsos": 3})
        return dict(("%s_%d" % (t, i), 1) for i in range(2))
    cfg = {"trava": {"sem_pulso_s": 1800.0, "paginando_s": 3600.0,
                     "ram_pct": 90.0}}
    estado["trava"] = {"breasts": 1}
    res, caso = _uma_serie_com_passos([], run_ts=_run, cfg=cfg,
                                      protocolos=["torax_mama"])
    _seq = [t for t, _m in ordem]
    checar(u"a travada foi para o FIM da lista, depois das outras",
           _seq[-1] == "breasts" and _seq.count("breasts") == 2
           and _seq.index("pleural_pericard_effusion") < len(_seq) - 1,
           str(ordem))
    checar(u"  e a retomada foi com o plano de memoria menor",
           ordem[-1] == ("breasts", True), str(ordem[-1:]))
    checar(u"  e a serie saiu com ela (destravou)",
           not res.get("erro") and not res.get("tasks_falharam"),
           str(res.get("tasks_falharam")))
    pr = caso.get("processamento") or {}
    checar(u"  e o caso registra o travamento, com a retomada «ok»",
           [(x.get("task"), x.get("retomada"))
            for x in pr.get("travamentos") or ()] == [("breasts", "ok")],
           str(pr.get("travamentos")))
    checar(u"os numeros do config chegam ao motor em MINUTOS",
           kw_vistos.get("breasts", [None])[0] == {
               "sem_pulso_min": 30.0, "paginando_min": 60.0, "ram_pct": 90.0},
           str(kw_vistos.get("breasts")))
    del ordem[:]
    estado["trava"] = {"breasts": 2}
    res, caso = _uma_serie_com_passos([], run_ts=_run, cfg=cfg,
                                      protocolos=["torax_mama"])
    tf = res.get("tasks_falharam") or []
    checar(u"travou de novo: a serie sai SEM ela (tasks_falharam, classe "
           u"travou), e o entregue sai",
           not res.get("erro") and [(f.get("task"), f.get("classe"))
                                    for f in tf] == [("breasts", "travou")],
           str(tf) + str(res.get("erro")))
    del ordem[:]
    import radai_tasks as _rtk
    estado["trava"] = {}

    def _run_base(ref, t, **k):
        if _rtk.familia_da_task(t) == "total":
            raise E.TaskTravada(t, "sem_pulso", {"sem_pulso_s": 900.0,
                                                 "limite_s": 900.0})
        return {"x_%s" % t: 1}
    res, caso = _uma_serie_com_passos([], run_ts=_run_base, cfg=cfg)
    checar(u"a BASE travada duas vezes derruba a serie, com o motivo",
           u"TRAVADA" in (res.get("erro") or u""), str(res.get("erro"))[:160])
    checar(u"ISCA: o dicionario do vigia como veio nao tem as chaves que o "
           u"motor le (a conversao e necessaria)",
           not ({"sem_pulso_min", "paginando_min"} & set(cfg["trava"]))
           and E.trava_efetiva(cfg["trava"])["sem_pulso_min"]
           == float(E.TRAVA_SEM_PULSO_MIN))
    velho = dict(L._CFG)
    try:
        L._CFG.clear()
        checar(u"sem a chave injetada, `None` (os numeros de fabrica do motor)",
               L._trava_do_lote() is None)
        L._CFG["trava"] = {"sem_pulso_min": 7, "paginando_s": 120,
                           "ram_pct": "80"}
        checar(u"  e a forma em minutos vence; os segundos viram minutos",
               L._trava_do_lote() == {"sem_pulso_min": 7.0,
                                      "paginando_min": 2.0, "ram_pct": 80.0},
               str(L._trava_do_lote()))
    finally:
        L._CFG.clear()
        L._CFG.update(velho)


def teste_o_falhou_do_lote_nao_leva_caminho_nem_uid():
    secao(u"o FALHOU do lote nao leva caminho nem UID")
    import inspect
    pasta = u"C:\\Pacientes\\FULANO_DE_TAL_123\\CT"
    uid = u"1.2.826.0.1.3680043.999.88887777"

    def _run(ref, t, **k):
        raise RuntimeError(u"serie %s: nao consegui ler %s\\IM0001.dcm"
                           % (uid, pasta))
    linhas = []
    res, _c = _uma_serie_com_passos([], run_ts=_run, log=linhas)
    err = res.get("erro") or u""
    checar(u"a serie falhou, e o erro diz o TIPO", err.startswith(
        u"RuntimeError"), err[:160])
    checar(u"  sem a pasta do paciente e sem o UID",
           u"FULANO_DE_TAL" not in err and uid not in err
           and u"<uid>" in err, err[:200])
    _f = [l for l in linhas if l.startswith(u"FALHOU")]
    checar(u"  e a linha FALHOU do log tambem",
           _f and u"FULANO_DE_TAL" not in _f[-1] and uid not in _f[-1],
           str(_f[-1:])[:200])
    src = inspect.getsource(L._uma_serie)
    alvo = u'res["erro"] = _motivo_do_erro(e)[:250]'
    ns = dict(vars(L))
    exec(compile(src.replace(alvo, u'res["erro"] = "%s: %s" % '
                             u'(type(e).__name__, str(e)[:200])'),
                 "<isca-falhou>", "exec"), ns)
    res_i, _c = _uma_serie_com_passos([], run_ts=_run, fn=ns["_uma_serie"])
    checar(u"ISCA: com a linha de antes, a pasta e o UID voltam (a checagem "
           u"sabe reprovar)", alvo in src
           and u"FULANO_DE_TAL" in (res_i.get("erro") or u""),
           (res_i.get("erro") or u"")[:160])


def teste_a_espessura_e_medida_na_normal_do_corte():
    secao(u"a espessura e medida na normal do corte (sagital, coronal)")

    class _Ds(object):
        def __init__(self, ipp, iop):
            self.ImagePositionPatient = ipp
            self.ImageOrientationPatient = iop
    ax = [1, 0, 0, 0, 1, 0]
    sag = [0, 1, 0, 0, 0, -1]
    cor = [1, 0, 0, 0, 0, -1]
    for nome, iop, passo, ipp_de in (
            (u"axial", ax, 3.0, lambda i: [-100.0, -100.0, i * 3.0]),
            (u"sagital", sag, 0.8, lambda i: [i * 0.8, -120.0, 50.0 + i * 0.01]),
            (u"coronal", cor, 2.0, lambda i: [-100.0, i * 2.0, 60.0])):
        s = {"_zs": set()}
        for i in range(20):
            s["_zs"].add(L._posicao_na_normal(_Ds(ipp_de(i), iop)))
        e = L._espessura_real(s)
        checar(u"%s: a espessura e o passo entre os cortes (%.2f mm)"
               % (nome, passo), e is not None and abs(e - passo) < 0.02,
               str(e))
    s = {"_zs": set(L._posicao_na_normal(_Ds([0.0, 0.0, i * 2.5], None))
                    for i in range(10))}
    checar(u"sem `ImageOrientationPatient`, fica o z",
           abs((L._espessura_real(s) or 0) - 2.5) < 0.02)
    s = {"_zs": set(round(50.0 + i * 0.01, 3) for i in range(20))}
    checar(u"ISCA: pelo z, a sagital daria menos de 0,1 mm (o defeito da P24)",
           (L._espessura_real(s) or 0) < 0.1 or L._espessura_real(s) is None,
           str(L._espessura_real(s)))


def teste_a_serie_do_lote_manda_o_toast_do_windows():
    secao(u"FD3: a serie do lote manda o toast do Windows (PowerShell dublado)")
    import inspect
    import threading as _th
    import time
    import radai_notify as N
    checar(u"a bateria roda com a notificacao DESARMADA (nenhum toast na "
           u"maquina de quem a roda)", N.ligada() is False)
    chamadas = []
    solta = _th.Event()
    terminou = [0]

    def _ps(titulo, texto):
        chamadas.append((titulo, texto))
        solta.wait(5.0)
        terminou[0] += 1
        return (True, u"")

    def _espera(cond, prazo=5.0):
        t = time.time()
        while time.time() - t < prazo and not cond():
            time.sleep(0.02)
        return cond()

    velho_mostrar = N.mostrar
    velho_env = os.environ.get("RADAI_NOTIFICACAO")
    os.environ["RADAI_NOTIFICACAO"] = "1"
    N.mostrar = _ps
    import radai_languages as _RL
    velho_idioma = _RL.padrao_efetivo
    _RL.padrao_efetivo = lambda: u"pt-BR"
    try:
        N.armar(False)
        _uma_serie_com_passos([], gravados=["oar", "full"])
        time.sleep(0.2)
        checar(u"desarmada, a serie do lote NAO chama o PowerShell (o "
               u"ambiente permite; falta a arma do vigia)", chamadas == [],
               str(chamadas))
        N.armar(True)
        res, _c = _uma_serie_com_passos([], gravados=["oar", "full"])
        _espera(lambda: chamadas)
        checar(u"sucesso: um toast, e a serie voltou ANTES de o PowerShell "
               u"terminar (o toast e numa thread)",
               len(chamadas) == 1 and terminou[0] == 0 and not res.get("erro"),
               str((len(chamadas), terminou[0], res.get("erro"))))
        solta.set()
        _espera(lambda: terminou[0] >= 1)
        uid8 = str(res.get("uid") or u"")[-8:]
        titulo, texto = chamadas[0] if chamadas else (u"", u"")
        checar(u"o toast de SUCESSO diz a serie (…uid8), o que foi gravado e "
               u"que e sugestao nao aprovada",
               u"pronta" in titulo and uid8 and (u"…" + uid8) in texto
               and u"RadAI_STUDY + FULL" in texto and u"não aprovada" in texto,
               str((titulo, texto)))
        checar(u"  sem caminho nem a pasta do paciente",
               u"\\" not in texto and u"/" not in texto
               and u"PAC_PASSOS" not in texto, texto)
        del chamadas[:]
        res2, _c2 = _uma_serie_com_passos([], falhar=True)
        _espera(lambda: chamadas)
        titulo2, texto2 = chamadas[0] if chamadas else (u"", u"")
        checar(u"erro: o toast diz que a serie nao saiu, pelo «Rodar agora»",
               bool(res2.get("erro")) and u"não saiu" in titulo2
               and u"Rodar agora" in texto2
               and (u"…" + str(res2.get("uid") or u"")[-8:]) in texto2,
               str((titulo2, texto2, res2.get("erro"))))
        checar(u"  sem a mensagem do erro (que pode trazer caminho e paciente)",
               u"parou de proposito" not in texto2
               and u"FULL/OAR" not in texto2, texto2)
        import radai_phrases as _RP
        _de = _RP.construir()["de"]
        _RL.padrao_efetivo = lambda: u"de"
        try:
            del chamadas[:]
            res4, _c4 = _uma_serie_com_passos([], gravados=["oar", "full"])
            _espera(lambda: chamadas)
        finally:
            _RL.padrao_efetivo = lambda: u"pt-BR"
        titulo4, texto4 = chamadas[0] if chamadas else (u"", u"")
        _k_ok = _RP.normalizar(N.FRASES["ok"])
        _k_tit = _RP.normalizar(N.FRASES["titulo_ok"])
        checar(u"com a estacao em alemao, o toast de sucesso sai em alemao, "
               u"pela entrada do dicionario",
               _k_ok in _de and _k_tit in _de and titulo4 == _de[_k_tit]
               and texto4 == _de[_k_ok].format(
                   str(res4.get("uid") or u"")[-8:], u"RadAI_STUDY + FULL"),
               str((titulo4, texto4)))
        del chamadas[:]
        N.FALHOU[0] = False
        N.mostrar = lambda t, x: (False, u"PowerShell saiu com 1 (dublado)")
        linhas = []
        res3, _c3 = _uma_serie_com_passos([], gravados=["oar", "full"],
                                          log=linhas)
        _espera(lambda: any(u"notificacao do Windows" in str(l)
                            for l in linhas))
        checar(u"o PowerShell que falha vira uma linha de log, e a serie SAI",
               not res3.get("erro") and sum(
                   1 for l in linhas
                   if u"notificacao do Windows: nao consegui" in str(l)) == 1,
               str([str(l)[:120] for l in linhas if u"notificacao" in str(l)]))
        N.mostrar = _ps
        del chamadas[:]
        src = inspect.getsource(L._uma_serie)
        alvo = u'_notificar_a_serie("ok"'
        ns = dict(vars(L))
        exec(compile(src.replace(alvo, u'(lambda *a, **k: None)("ok"', 1),
                     "<isca-toast>", "exec"), ns)
        _uma_serie_com_passos([], gravados=["oar", "full"],
                              fn=ns["_uma_serie"])
        time.sleep(0.3)
        checar(u"ISCA: sem a chamada do sucesso, nenhum toast (a checagem "
               u"reprova)", alvo in src and chamadas == [], str(chamadas))
        solta.clear()
        terminou[0] = 0
        velho_disparar = N.disparar
        N.disparar = lambda t, x, mostrar_fn=None, log=None: (
            N.em_segundo_plano(t, x, mostrar_fn, log) or True)
        _th.Timer(0.5, solta.set).start()
        try:
            _uma_serie_com_passos([], gravados=["oar", "full"])
        finally:
            N.disparar = velho_disparar
        checar(u"ISCA: o toast SINCRONO so volta depois do PowerShell (a "
               u"checagem «voltou antes» reprovaria)", terminou[0] == 1,
               str(terminou[0]))
    finally:
        solta.set()
        N.mostrar = velho_mostrar
        _RL.padrao_efetivo = velho_idioma
        N.armar(False)
        N.FALHOU[0] = False
        if velho_env is None:
            os.environ.pop("RADAI_NOTIFICACAO", None)
        else:
            os.environ["RADAI_NOTIFICACAO"] = velho_env


def teste_o_caso_leva_o_processamento_da_v83():
    secao(u"o caso leva o processamento da v8.3")
    import radai_records as RG
    esc = L.escolha_da_serie({"modo": "perso", "protocolos": ["torax_mama"],
                              "tasks": {"abdominal_muscles": 0},
                              "comparacao": {"ts": 1}})
    meta = {"regras_de_gravacao": [
        {"regra": u"R1 borda do campo", "nome": "lung_left", "cm3": 12.0,
         "inteira": True, "motivo": u"grande na borda cranial"}],
        "ilhas_em_revisao": [{"nome": "liver", "ilhas": 2, "cm3": 3.1}]}
    linhas = [u"   TS breasts memoria: 9.0 GB livres no inicio, 2.0 no pico "
              u"de uso (-7.0 GB com tudo o que rodou junto), 88% da estacao "
              u"no pior momento",
              u"   TS total_v2 memoria: 10.0 GB livres no inicio, 0.5 no pico "
              u"de uso (-9.5 GB com tudo o que rodou junto), 97% da estacao "
              u"no pior momento"]
    pr = L.processamento_do_caso(
        esc, "perso", tasks=["total_v2", "trunk_cavities", "breasts"],
        travamentos=[{"task": "breasts", "motivo": "sem_pulso",
                      "retomada": "ok", "onde": "parte 1/2"}],
        recortes={"breasts": {"ancora": "torax", "margem_mm": 30.0,
                              "zyx": [1, 2, 3, 4, 5, 6]}},
        meta_entrega=meta, oar_fora=["heart"],
        niveis={"rodam": False, "motivo": u"pela escolha"},
        do_job={"plano": {"modo": "cpu"},
                "_planos": {"breasts": {"modo": "cpu", "plano_menor": True,
                                        "x": 1}}},
        log_motor=linhas, dispositivo="cpu")
    checar(u"so chaves que o registro conhece",
           not (set(pr) - set(RG.CAMPOS_DO_PROCESSAMENTO)), str(sorted(pr)))
    checar(u"o modo, os protocolos, a chave desligada e a comparacao",
           pr.get("modo") == "perso" and pr.get("protocolos") == ["torax_mama"]
           and pr.get("tasks_desligadas") == ["abdominal_muscles"]
           and pr.get("comparacao", {}).get("ts") == 1, str(pr)[:200])
    checar(u"as remocoes R1-R4 do entregue, pela funcao do vigia (a regra "
           u"CURTA, e a frase inteira no comeco do motivo)",
           pr.get("remocoes") == RG.remocoes_do_full(
               meta["regras_de_gravacao"])
           and [(x.get("regra"), x.get("nome"), x.get("volume_cm3"))
                for x in pr.get("remocoes") or ()]
           == [("R1", "lung_left", 12.0)]
           and u"R1 borda do campo" in pr["remocoes"][0].get("motivo", u""),
           str(pr.get("remocoes")))
    checar(u"as ilhas mantidas para revisao vao ao PROCESSAMENTO (a funcao "
           u"do vigia)",
           pr.get("ilhas_em_revisao") == [{"nome": "liver", "ilhas": 2,
                                           "cm3": 3.1}],
           str(pr.get("ilhas_em_revisao")))
    checar(u"o travamento, o clip-box (sem a caixa em voxel) e o «x»",
           pr.get("travamentos", [{}])[0].get("retomada") == "ok"
           and pr.get("clip_box", {}).get("breasts", {}).get("usado") is True
           and "zyx" not in pr.get("clip_box", {}).get("breasts", {})
           and pr.get("oar_fora") == ["heart"], str(pr)[:300])
    _pm = pr.get("pico_memoria") or {}
    checar(u"o pico de memoria e o PIOR momento da serie, pela leitura do "
           u"vigia (`radai_records.pico_de_memoria`)",
           _pm == RG.pico_de_memoria(linhas) and _pm.get("ram_pct") == 97.0
           and _pm.get("task") == "total_v2"
           and _pm.get("livre_min_gb") == 0.5, str(_pm))
    checar(u"o plano do motor, solto, e o de cada task em `por_task` (so as "
           u"chaves de plano)",
           pr.get("plano_dispositivo", {}).get("modo") == "cpu"
           and pr.get("plano_dispositivo", {}).get("por_task", {}).get(
               "breasts") == {"modo": "cpu", "plano_menor": True},
           str(pr.get("plano_dispositivo")))
    checar(u"a serie sem modo (a lista do chamador) grava modo `None`",
           L.processamento_do_caso({}, "lista").get("modo") is None)
    _au = L.processamento_do_caso(L.escolha_da_serie({"modo": "auto"}),
                                  "auto", tasks=["total_v3"])
    checar(u"no AUTO, sem o `meta` do entregue: sem `oar_fora`, sem "
           u"`remocoes` e sem `ilhas_em_revisao` (fora, e nao vazios)",
           not ({"oar_fora", "remocoes", "ilhas_em_revisao"} & set(_au)),
           str(sorted(_au)))
    res, caso = _uma_serie_com_passos([], meta=meta)
    _pr = caso.get("processamento") or {}
    checar(u"pela porta: as remocoes do `meta_do_full` chegam ao caso",
           [r.get("nome") for r in _pr.get("remocoes") or ()]
           == ["lung_left"], str(_pr.get("remocoes")))
    _ac = [a for a in caso.get("achados") or ()
           if a.get("tipo") == "ilha_em_revisao"]
    checar(u"  e as ilhas mantidas para revisao vao ao processamento, e nao "
           u"como ACHADO do caso",
           [x.get("nome") for x in _pr.get("ilhas_em_revisao") or ()]
           == ["liver"] and not _ac,
           str((_pr.get("ilhas_em_revisao"), _ac)))
    import inspect
    src = inspect.getsource(L._uma_serie)
    alvo = u"                processamento=_proc,\n"
    ns = dict(vars(L))
    exec(compile(src.replace(alvo, u""), "<isca-proc>", "exec"), ns)
    _r, caso_i = _uma_serie_com_passos([], meta=meta, fn=ns["_uma_serie"])
    checar(u"ISCA: sem `processamento=` na chamada, o caso sai sem ele (a "
           u"checagem sabe reprovar)", alvo in src
           and not caso_i.get("processamento"))



_CHAVES_DUBLES_JS = u"""
var OPC_CT = %(opc)s;
function _opcDaSerie(){ return OPC_CT }
function E(){ return {modo:'perso', prot:{}, p3d:{}, mao:{}, comp:{},
                      oar_fora:{}, livre:false} }
var S = {};
"""

_CHAVES_RODA_JS = u"""
function ligadas(e){ return Object.keys(tasksLigadas(S, e)).sort() }
function foto(e){ return {ligadas: ligadas(e), finais: chavesFinais(S, e),
                          protocolos: protocolosLigados(S, e), livre: !!e.livre} }
var R = {prot: {}};
(OPC_CT.protocolos || []).forEach(function(p){
 var e = E(); ligarProtocolo(S, e, p.cod, true); R.prot[p.cod] = foto(e);
});
var cen = %(cen)s;
var e = E(); R.fabrica = foto(e);
e = E(); ligarProtocolo(S, e, cen.um, true); ligarProtocolo(S, e, cen.outro, true);
R.outro = foto(e);
e = E(); ligarProtocolo(S, e, cen.um, true); chaveDaTask(S, e, cen.avulsa, true);
R.mao_liga = foto(e);
e = E(); ligarProtocolo(S, e, cen.um, true); chaveDaTask(S, e, cen.do_um, false);
R.mao_desliga = foto(e);
e = E(); ligarProtocolo(S, e, cen.um, true); ligarProtocolo(S, e, cen.um, false);
R.desliga = foto(e);
e = E(); ligarSelecaoLivre(S, e, true); R.livre = foto(e);
ligarSelecaoLivre(S, e, false); R.livre_fora = foto(e);
e = E(); e.comp = {ts: 1}; ligarProtocolo(S, e, cen.um, true);
ligarProtocolo3d(S, e, cen.p3d, true);
R.p3d = foto(e); R.p3d.p3d = Object.keys(e.p3d || {}); R.p3d.comp = e.comp;
e = E(); chaveDaTask(S, e, 'lung_nodules', true); R.achado = foto(e);
var e4 = E(); e4.comp = {ts:1, nv:1, cads:1, mse:1};
R.comp = comparacaoDe(S, e4);
console.log('JSON:' + JSON.stringify(R));
"""


def _rodar_js_no_node(js, prefixo=u"radai_t_chaves_"):
    import json as _json
    import shutil as _sh
    import subprocess as _sp
    node = _sh.which("node")
    if not node:
        return None, u"PULADO -- sem node"
    tmp = tempfile.mkdtemp(prefix=prefixo)
    try:
        arq = os.path.join(tmp, "t.js")
        io.open(arq, "w", encoding="utf-8").write(js)
        r = _sp.run([node, arq], capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=60)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for ln in reversed((r.stdout or u"").splitlines()):
        if ln.startswith(u"JSON:"):
            return _json.loads(ln[5:]), u""
    return None, ((r.stderr or u"") + (r.stdout or u""))[-300:]


def teste_as_chaves_da_tela_e_o_servidor_concordam():
    secao(u"as chaves da tela, a «Seleção livre» e o servidor concordam (v8.5)")
    import json as _json
    import radai_modes as _md
    pag = L.PAGINA
    nomes = (u"_porTask", u"_arrastavel", u"tasksLigadas", u"_soAsDele",
             u"ligarProtocolo", u"ligarSelecaoLivre", u"ligarProtocolo3d",
             u"chaveDaTask", u"protocolosLigados", u"chavesFinais",
             u"_compBloqueada", u"comparacaoDe", u"_ppsDaSerie",
             u"_ppDaSerie", u"_travadasPeloPp")
    fontes = [_corpo_js(pag, n) for n in nomes]
    checar(u"as funcoes do modelo das chaves estao na pagina", all(fontes),
           u", ".join(n for n, f in zip(nomes, fontes) if not f))
    if not all(fontes):
        return
    opc = L.opcoes_da_tela("CT")
    por = dict((x["task"], x) for x in opc["tasks"])

    def arrastaveis(lista):
        return set(x for x in lista if x in por and not por[x].get("achado")
                   and por[x].get("permitida") is not False)
    protos = dict((p["cod"], p) for p in opc["protocolos"])
    um, outro = u"torax_mama", u"abdome"
    do_um = sorted(arrastaveis(list(protos[um].get("tasks") or ())))
    avulsa = [x["task"] for x in opc["tasks"]
              if not x.get("achado") and x.get("permitida") is not False
              and not x.get("protocolos") and x["task"] not in do_um
              and x["task"] in _md.tasks_do_personalizado((), {x["task"]: 1},
                                                          "CT")][0]
    cen = {"um": um, "outro": outro, "avulsa": avulsa, "do_um": do_um[0],
           "p3d": opc["protocolos_3d"][0]["cod"]}
    js = (_CHAVES_DUBLES_JS % {"opc": _json.dumps(opc, default=str)}
          + u"\n".join(fontes) + _CHAVES_RODA_JS % {"cen": _json.dumps(cen)})
    res, erro = _rodar_js_no_node(js)
    if erro.startswith(u"PULADO"):
        checar(u"`node` nesta maquina (PULADO: sem ele o JS nao roda aqui)",
               True)
        return
    checar(u"o modelo das chaves executa no node", res is not None, erro)
    if res is None:
        return
    permitidas, achados = L._achados_e_permitidas()
    base = _md.base_de("CT")

    def servidor(r):
        return set(_md.tasks_do_personalizado(
            r.get("protocolos") or (), dict(r.get("finais") or {}), "CT",
            permitidas=permitidas, achados=achados,
            catalogo=L._catalogo_de_tasks())) - {base}

    def tela(r):
        return set(x for x in r.get("ligadas") or ()
                   if x != L.CHAVE_DOS_NIVEIS
                   and x not in L.CHAVES_DOS_MOTORES_DO_FULL)
    for cod, r in sorted(res["prot"].items()):
        p = protos[cod]
        quer = arrastaveis(list(p.get("tasks") or ()) + list(p.get("motores") or ()))
        checar(u"[%s] o protocolo liga SO as tasks dele" % cod,
               set(r["ligadas"]) == quer,
               u"tela=%s protocolo=%s" % (sorted(r["ligadas"]), sorted(quer)))
        checar(u"[%s]   e o servidor roda o mesmo, com as chaves da tela" % cod,
               tela(r) == servidor(r),
               u"tela=%s servidor=%s" % (sorted(tela(r)), sorted(servidor(r))))
        checar(u"[%s]   e a chave final e 1 so no que liga, 0 no resto" % cod,
               set(r["finais"]) == set(por)
               and set(k for k, v in r["finais"].items() if v) == set(r["ligadas"]))
    fab = arrastaveis(opc.get("ligadas_de_fabrica") or ())
    checar(u"de fabrica: a «Seleção livre» desligada e so as de fabrica",
           res["fabrica"]["livre"] is False
           and set(res["fabrica"]["ligadas"]) == fab, str(res["fabrica"]))
    q_outro = arrastaveis(list(protos[outro].get("tasks") or ())
                          + list(protos[outro].get("motores") or ()))
    checar(u"escolher OUTRO protocolo liga so as tasks dele",
           res["outro"]["protocolos"] == [outro]
           and set(res["outro"]["ligadas"]) == q_outro, str(res["outro"]))
    checar(u"mexer a mao numa task desliga o protocolo e liga a «Seleção livre»",
           res["mao_liga"]["protocolos"] == [] and res["mao_liga"]["livre"]
           is True and set(res["mao_liga"]["ligadas"]) == set(do_um) | {avulsa},
           str(res["mao_liga"]))
    checar(u"  e desligar uma do protocolo tambem, e as outras ficam",
           res["mao_desliga"]["protocolos"] == [] and res["mao_desliga"]["livre"]
           and set(res["mao_desliga"]["ligadas"]) == set(do_um) - {do_um[0]},
           str(res["mao_desliga"]))
    checar(u"  e o servidor concorda com a selecao livre",
           tela(res["mao_liga"]) == servidor(res["mao_liga"])
           and tela(res["mao_desliga"]) == servidor(res["mao_desliga"]))
    checar(u"desligar o protocolo volta ao de fabrica",
           set(res["desliga"]["ligadas"]) == fab and not res["desliga"]["protocolos"],
           str(res["desliga"]))
    checar(u"ligar a «Seleção livre» guarda o que estava ligado",
           res["livre"]["livre"] is True and set(res["livre"]["ligadas"]) == fab)
    checar(u"  e desliga-la volta ao de fabrica", res["livre_fora"]["livre"] is False
           and set(res["livre_fora"]["ligadas"]) == fab)
    checar(u"o protocolo de estudo 3D segue a mesma regra: tira o RT e desliga "
           u"as outras, e zera a comparacao",
           res["p3d"]["protocolos"] == [] and res["p3d"]["ligadas"] == []
           and res["p3d"]["p3d"] == [cen["p3d"]] and res["p3d"]["comp"] == {},
           str(res["p3d"]))
    checar(u"a task de ACHADO so liga pela chave dela (o ato declarado)",
           u"lung_nodules" in res["achado"]["ligadas"]
           and all(u"lung_nodules" not in r["ligadas"]
                   for r in res["prot"].values()))
    if u"cabeca_pescoco" in res["prot"]:
        checar(u"o Cabeca e Pescoco avancado liga os niveis cervicais (motor)",
               L.CHAVE_DOS_NIVEIS in res["prot"][u"cabeca_pescoco"]["ligadas"])
    esperada = dict((c["cod"], 0 if (c.get("instalado") is False
                                     or c.get("disponivel") is False) else 1)
                    for c in opc["comparacao"])
    checar(u"a comparacao pedida vai em 1 so no modelo que pode rodar",
           res["comp"] == esperada, u"%s != %s" % (res["comp"], esperada))

    forjado = _json.loads(_json.dumps(opc, default=str))
    for p in forjado["protocolos"]:
        if p["cod"] == um:
            p["tasks"] = list(p["tasks"]) + [u"lung_nodules"]
    js_ok = (_CHAVES_DUBLES_JS % {"opc": _json.dumps(forjado)}
             + u"\n".join(fontes) + _CHAVES_RODA_JS % {"cen": _json.dumps(cen)})
    r_ok, _e1 = _rodar_js_no_node(js_ok)
    r_isca, _e2 = _rodar_js_no_node(js_ok.replace(u"!t.achado", u"true"))
    checar(u"um protocolo forjado com achado NAO arrasta o achado na tela",
           r_ok is not None
           and u"lung_nodules" not in r_ok["prot"][um]["ligadas"], _e1)
    checar(u"  (isca) sem o `!t.achado`, a tela o arrastaria -- a checagem "
           u"discrimina",
           u"!t.achado" in js_ok and r_isca is not None
           and u"lung_nodules" in r_isca["prot"][um]["ligadas"], _e2)
    r_velho, _e3 = _rodar_js_no_node(js.replace(
        u"if(!e.livre) ligarSelecaoLivre(s, e, true);", u""))
    checar(u"  (isca) sem a «Seleção livre» na chave a mao, o protocolo fica "
           u"ligado -- a checagem discrimina",
           r_velho is not None and r_velho["mao_liga"]["protocolos"] == [um], _e3)


def teste_a_linha_da_serie_e_o_modal_do_turno_da_v83():
    secao(u"a linha da serie e o modal do turno (v8.3)")
    pag = L._pagina()
    cod = _sem_comentario_js(L.PAGINA)
    for nome in (u"pedirEstudo", u"marcarAMao", u"painelEstudos", u"celulaProc",
                 u"notaProc", u"_preMarcaveis", u"_nomesDosEstudos",
                 u"_grupoEstudo", u"_acertarCaixas"):
        checar(u"a funcao da v8.2 `%s` saiu" % nome,
               (u"function %s(" % nome) not in cod and (nome + u"(") not in cod)
    checar(u"  e o botao «escolher estudos» (`data-md-ed`) tambem",
           u"data-md-ed" not in cod and u"escolher estudos" not in cod)
    corpo_pl = _sem_comentario_js(_corpo_js(L.PAGINA, u"payloadDaSerie"))
    checar(u"o pedido leva o MODO sempre, e os campos da v8.2 saem dele",
           u"d.modo = modoDe(s)" in corpo_pl
           and u"CAMPOS_DA_ESCOLHA.forEach" in corpo_pl
           and all(u"'%s'" % k in cod for k in (u"estudos", u"tasks_extra",
                                                u"motores_extra")),
           corpo_pl[:200])
    checar(u"  e so o PERSONALIZADO leva protocolos, chaves, comparacao e o «x»",
           u"d.modo === 'perso'" in corpo_pl and u"d.oar_fora" in corpo_pl
           and u"d.comparacao" in corpo_pl and u"d.tasks = chavesFinais" in corpo_pl)
    i = pag.find(u"<tr><th>Paciente</th>")
    cab = pag[i:pag.find(u"</tr>", i)]
    checar(u"a coluna do modo e a ULTIMA, e a das acoes a penultima",
           cab.endswith(u"<th>Ações</th><th>Modo</th>")
           and u"Processamento" not in cab, cab[-80:])
    lin = _corpo_js(L.PAGINA, u"linhaDaSerie")
    checar(u"  e a linha desenha as duas nessa ordem, a do modo por ultimo",
           lin.find(u"td class=\"acoes\"") < lin.find(u"td class=\"modo\"")
           and u"celulaModo(i)" in lin and u"'</td></tr>'" in lin)
    ms = _corpo_js(L.PAGINA, u"_montarSeletores")
    checar(u"o seletor e o `uiSegmentado` da casca (desliza e embaralha), e o nao "
           u"incluido e desabilitado",
           u"uiSegmentado(sel, {embaralhar: true})" in ms and u"b.disabled = true" in ms
           and u"!INCL[i]" in ms)
    cm = _corpo_js(L.PAGINA, u"celulaModo")
    checar(u"  e cada opcao leva ao balao o texto que o modo ja tem",
           u"data-ui-balao" in cm and u"x.ajuda" in cm)
    pt = _corpo_js(L.PAGINA, u"pintarTabela")
    checar(u"  e os seletores soltam o `resize` antes de a tabela ser trocada",
           0 <= pt.find(u"_soltarSeletores();") < pt.find(u"el('tab').innerHTML=")
           and u"removeEventListener('resize'" in _corpo_js(L.PAGINA, u"_soltarSeletores"))
    checar(u"  e o modo e decidido na inclusao: nasce AUTO",
           u"if(!e.modo) e.modo = MODO_DE_FABRICA;" in _corpo_js(L.PAGINA,
                                                                 u"porNoCarrinho"))
    checar(u"a chave e `role=\"switch\"`, o `label.sw` verde",
           u'role="switch"' in _corpo_js(L.PAGINA, u"_swHTML")
           and u".p4 label.sw input:checked + .tr{background:var(--ok)" in pag)
    checar(u"a previa da entrega e pedida ao servidor, que decide",
           u"fetch('/api/lote/previa_da_entrega'" in cod)
    corpo = L._corpo_da_folha_do_turno()
    checar(u"o molde da folha e um `<template>` (sem ids duplicados no DOM)",
           corpo.startswith(u'<template id="ov_folha_corpo">')
           and corpo.rstrip().endswith(u"</template>"))
    for campo in (u'id="ov_root"', u'id="ov_mod"', u'id="ov_dias"',
                  u'data-ui-fav="ov_root"', u'data-ov-mod="CT,MR"'):
        checar(u"  e leva `%s`" % campo, campo in corpo)
    checar(u"  e nao leva mais a caixa de pausar servicos",
           u'id="ov_pausar"' not in corpo and u"ov-servicos" not in corpo)
    ap = _sem_comentario_js(_corpo_js(L.PAGINA, u"_ovAbrirPastas"))
    checar(u"  e «Procurar…» abre o explorador da casca, e nao um seletor "
           u"proprio", u"uiExplorador(" in ap and u'id="ov_pastas"' not in corpo
           and u"/api/pastas'" not in _corpo_js(L.PAGINA, u"_ovAbrirPastas"),
           ap[:200])
    checar(u"  e a estrela da pasta favorita e ligada quando a folha abre",
           u"uiFavoritaLigar(" in _corpo_js(L.PAGINA, u"folhaOvernight"))
    ini = _sem_comentario_js(_corpo_js(L.PAGINA, u"ovIniciar"))
    checar(u"«Salvar e incluir na fila» grava pela rota da configuracao COM a trava "
           u"do ROOT", u"fetch('/api/config'" in ini
           and u"confirmar_root: true" in ini, ini[:200])
    checar(u"  e pede a recarga a quente antes de por o card",
           u"fetch('/api/reiniciar'" in ini
           and 0 <= ini.find(u"fetch('/api/reiniciar'") < ini.find(u"_ovPorNaFila("))
    checar(u"  e NAO espera a recarga por polling na tela (quem espera e a "
           u"rota do turno)", u"_ovEsperarRecarga" not in cod
           and u"n > 20" not in ini, ini[:200])
    pn = _sem_comentario_js(_corpo_js(L.PAGINA, u"_ovPorNaFila"))
    checar(u"incluir o turno só põe o card na fila e espera INICIAR",
           u"filaOvernight(true)" in pn
           and u"/api/overnight/iniciar" not in pn
           and u"/api/pipeline/iniciar" not in pn
           and u"aguardando INICIAR" in pn)
    checar(u"o texto de turno aberto continua dizendo quando a recarga está pendente",
           u"a configuração nova vale quando a série em curso terminar"
           in _corpo_js(L.PAGINA, u"_ovTextoAberto"))
    fe = _sem_comentario_js(_corpo_js(L.PAGINA, u"filaEstado"))
    checar(u"  e continua dizendo nas voltas da fila (o `/api/status` leva "
           u"`recarga_pendente`)", u"st.recarga_pendente" in fe, fe[:200])
    checar(u"a folha do turno so tem «Cancelar» e «Salvar e incluir na fila»",
           u"ov_bt_sem" not in cod and u"Iniciar sem salvar" not in cod
           and u"_ovTemporarios" not in cod, u"o terceiro botao voltou")
    fo = _sem_comentario_js(_corpo_js(L.PAGINA, u"filaOvernight"))
    checar(u"  e o card do turno nao leva valores de uma noite so",
           u"temporarios" not in fo and u"temporarios" not in ini, fo[:240])
    es = _sem_comentario_js(_corpo_js(L.PAGINA, u"_ovEstado"))
    checar(u"  e «Salvar e incluir na fila» exige o config lido e o laudo bom",
           u"sim.disabled = !(OV.cfg && _ovLaudoBom())" in es, es[:240])
    fp = _sem_comentario_js(_corpo_js(L.PAGINA, u"filaEstadoPintar"))
    checar(u"o cartao diz quando o card do turno FALHOU",
           u"cardTurno.estado === 'falhou'" in fp
           and u"O turno não abriu" in fp, fp[:240])
    checar(u"o seletor de pasta da folha e o explorador da casca (POST) e o "
           u"laudo o de `/api/config/testar`",
           u"uiExplorador(" in _corpo_js(L.PAGINA, u"_ovAbrirPastas")
           and u"fetch('/api/config/testar', {method:'POST'" in cod)
    import inspect
    import radai_panel as _pn
    fonte_pn = inspect.getsource(_pn)
    fonte_vg = io.open(os.path.join(os.path.dirname(L.__file__),
                                    "radai_watcher.py"), encoding="utf-8").read()
    for rota, fonte in ((u'"/api/config"', fonte_pn), (u'"/api/config/testar"', fonte_pn),
                        (u'"/api/pastas"', fonte_pn), (u'"/api/reiniciar"', fonte_pn),
                        (u'"/api/overnight/iniciar"', fonte_vg),
                        (u'"/api/overnight/encerrar"', fonte_vg)):
        checar(u"  e a rota %s existe no servidor" % rota, rota in fonte)
    lig = _corpo_js(L.PAGINA, u"_ovLigar")
    _ent = (lig.split(u"if(ev.key === 'Enter'){", 1)[1].split(u"return;", 1)[0]
            if u"if(ev.key === 'Enter'){" in lig else u"")
    checar(u"o Enter de dentro da folha nao confirma (captura no veu)",
           _ent.lstrip().startswith(u"ev.stopPropagation();")
           and u"addEventListener('keydown', tecla, true)" in lig, _ent[:160])
    checar(u"  e o «Salvar e incluir na fila» volta habilitado quando a folha fecha",
           u"sim.disabled = false" in _corpo_js(L.PAGINA, u"_ovSemBotao")
           and u"sim.disabled = true" in _corpo_js(L.PAGINA, u"_ovTravarSalvar"))



_GRADE_AN = (40, 64, 64)
_ESPAC_AN = (4.0, 4.0, 5.0)


def _bloco_an(z0, z1, y0, y1, x0, x1):
    import numpy as np
    m = np.zeros(_GRADE_AN, dtype=bool)
    m[z0:z1, y0:y1, x0:x1] = True
    return m


def _fantoma_anat(regioes):
    amig, cru = {}, {}
    if "cabeca" in regioes:
        amig["brain"] = _bloco_an(24, 39, 20, 32, 20, 32)
    if "pescoco" in regioes:
        amig["vertebrae_C2"] = _bloco_an(34, 38, 40, 45, 30, 35)
        amig["vertebrae_C3"] = _bloco_an(30, 34, 40, 45, 30, 35)
        amig["vertebrae_C4"] = _bloco_an(26, 30, 40, 45, 30, 35)
        amig["mandible"] = _bloco_an(28, 38, 46, 56, 25, 40)
    if "torax" in regioes:
        amig["lung_left"] = _bloco_an(8, 23, 10, 30, 40, 50)
        amig["lung_right"] = _bloco_an(8, 23, 10, 30, 14, 24)
        cru["clavicula_left"] = _bloco_an(22, 24, 5, 8, 40, 50)
        cru["clavicula_right"] = _bloco_an(22, 24, 5, 8, 14, 24)
        cru["scapula_left"] = _bloco_an(12, 20, 40, 45, 45, 55)
        cru["scapula_right"] = _bloco_an(12, 20, 40, 45, 9, 19)
    if "pelve" in regioes:
        amig["hip_left"] = _bloco_an(0, 6, 20, 40, 40, 55)
        amig["hip_right"] = _bloco_an(0, 6, 20, 40, 9, 24)
    if "coracao" in regioes:
        amig["heart"] = _bloco_an(8, 18, 30, 45, 25, 40)
    if "coracao_pequeno" in regioes:
        amig["heart"] = _bloco_an(8, 13, 30, 40, 25, 37)
    amig.setdefault("liver", _bloco_an(10, 20, 20, 30, 20, 30))
    c = dict(cru)
    c.update(amig)
    return amig, {"total_v3": c}


def _grade_anat():
    import numpy as np
    import SimpleITK as sitk
    import radai_geom
    img = sitk.GetImageFromArray(np.zeros(_GRADE_AN, dtype=np.int16))
    img.SetSpacing(_ESPAC_AN)
    return radai_geom.Grade.de_sitk(img)


def _chama_nome(fn, nome):
    import ast
    return fn is not None and any(
        isinstance(c, ast.Call)
        and (getattr(c.func, "id", None) == nome
             or getattr(c.func, "attr", None) == nome)
        for c in ast.walk(fn))


def _funcoes_de(fonte):
    import ast
    return dict((n.name, n) for n in ast.walk(ast.parse(fonte))
                if isinstance(n, ast.FunctionDef))


def _composicao_unica(vig, lote, topo):
    ruins = []
    fv, fl, ft = _funcoes_de(vig), _funcoes_de(lote), _funcoes_de(topo)
    an = ft.get("anatomia_da_base")
    if an is None:
        ruins.append(u"radai_topography.anatomia_da_base nao existe")
    else:
        for m in ("regioes_no_campo", "pescoco_no_campo",
                  "torax_identificado", "coracao_do_modelo_cm3"):
            if not _chama_nome(an, m):
                ruins.append(u"anatomia_da_base nao chama `%s`" % m)
    if not _chama_nome(ft.get("coracao_do_modelo_cm3"), "_volume_cm3"):
        ruins.append(u"o coracao nao e contado por `engine._volume_cm3` "
                     u"(a conta do portao R4)")
    if not _chama_nome(fv.get("_tasks_pela_anatomia"), "anatomia_da_base"):
        ruins.append(u"o vigia (`_tasks_pela_anatomia`) nao chama "
                     u"`anatomia_da_base`")
    if not _chama_nome(fl.get("_uma_serie"), "anatomia_da_base"):
        ruins.append(u"o lote (`_uma_serie`) nao chama `anatomia_da_base`")
    for nome, fs, arq in (("regioes_pela_anatomia", fv, "radai_watcher"),
                          ("coracao_do_modelo_cm3", fv, "radai_watcher"),
                          ("regioes_pela_anatomia", fl, "radai_batch"),
                          ("_coracao_do_modelo_cm3", fl, "radai_batch")):
        if nome in fs:
            ruins.append(u"a copia `%s.%s` voltou" % (arq, nome))
    for fn_nome, fs, arq in (("_tasks_pela_anatomia", fv, "vigia"),
                             ("_uma_serie", fl, "lote")):
        for m in ("regioes_no_campo", "torax_identificado", "_volume_cm3",
                  "_cm3_da_mascara"):
            if _chama_nome(fs.get(fn_nome), m):
                ruins.append(u"o %s mede `%s` por conta propria" % (arq, m))
    return ruins


def teste_a_anatomia_da_base_e_uma_so_nas_duas_portas():
    secao(u"a anatomia da base e uma funcao so, nas duas portas")
    import radai_topography as TP
    import radai_modes as MD
    vig = io.open(_componentes.fonte("app/radai_watcher.py"),
                  encoding="utf-8").read()
    lote = lote_py_txt()
    topo = io.open(_componentes.fonte("app/radai_topography.py"),
                   encoding="utf-8").read()

    ruins = _composicao_unica(vig, lote, topo)
    checar(u"UMA composicao (`radai_topography.anatomia_da_base`), chamada "
           u"pelo vigia e pelo lote, sem copia em nenhum dos dois",
           not ruins, u"; ".join(ruins))
    _isca_lote = lote.replace(
        u"\ndef _uma_serie(",
        u"\ndef regioes_pela_anatomia(masks, grade, cruas=None):\n"
        u"    return (), [], None, None\n\n\ndef _uma_serie(", 1)
    checar(u"  ISCA: a copia de volta no lote e acusada",
           _isca_lote != lote
           and any(u"radai_batch.regioes_pela_anatomia" in r
                   for r in _composicao_unica(vig, _isca_lote, topo)))
    _isca_vig = vig.replace(u"anatomia_da_base(", u"outra_anatomia(")
    checar(u"  ISCA: o vigia sem a chamada comum e acusado",
           _isca_vig != vig
           and any(u"o vigia" in r
                   for r in _composicao_unica(_isca_vig, lote, topo)))
    import ast
    _tops = [n for n in ast.parse(topo).body
             if isinstance(n, (ast.Import, ast.ImportFrom))]
    _mods = sorted(set(
        (a.name.split(".")[0] for n in _tops if isinstance(n, ast.Import)
         for a in n.names)) | set(
        (n.module or "").split(".")[0] for n in _tops
        if isinstance(n, ast.ImportFrom)))
    checar(u"  e `radai_topography` continua so biblioteca padrao no topo "
           u"(o motor e importado na medida)",
           set(_mods) <= set(("re", "unicodedata", "sys", "os")), str(_mods))

    fn = getattr(TP, "anatomia_da_base", None)
    if fn is None:
        checar(u"a funcao comum existe para medir os fantomas", False)
        return
    grade = _grade_anat()
    permitidas, achados = L._achados_e_permitidas()
    cat = L._catalogo_de_tasks()
    _CP = ("head_glands_cavities", "headneck_muscles",
           "headneck_bones_vessels", "head_muscles", "craniofacial_structures")
    _CR = ("head_glands_cavities", "craniofacial_structures")
    casos = (
        (u"torax (pulmao + clavicula + escapula)", {"torax"}, ("torax",),
         ("trunk_cavities", "breasts", "pleural_pericard_effusion")),
        (u"pelve", {"pelve"}, ("pelve",), ("trunk_cavities",)),
        (u"pescoco sem encefalo (C2, C3 e C4)", {"pescoco"},
         ("cabeca_pescoco",), _CP),
        (u"CRANIO sem pescoco (encefalo, nenhuma cervical)", {"cabeca"},
         ("cranio",), _CR),
        (u"cranio COM pescoco: so cabeca e pescoco (a lista contem a do "
         u"cranio)", {"cabeca", "pescoco"}, ("cabeca_pescoco",), _CP),
        (u"coracao do modelo com 180 cm3, sem torax", {"coracao"}, (),
         ("trunk_cavities",)),
        (u"coracao de 48 cm3 (abaixo do piso)", {"coracao_pequeno"}, (), ()),
    )

    def _medir(f, regs):
        masks, cruas = _fantoma_anat(regs)
        return f(masks, grade, cruas=cruas)

    for rot, regs, esperadas, tasks in casos:
        an = _medir(fn, regs)
        checar(u"%s -> regioes %s" % (rot, u", ".join(esperadas) or u"nenhuma"),
               tuple(an.get("regioes") or ()) == tuple(esperadas),
               u"%s | %s" % (an.get("regioes"),
                             u" / ".join(an.get("laudo") or [])[:240]))
        cor = an.get("coracao_cm3")
        vig_t, _fora, _n = TP.tasks_da_anatomia(
            an.get("regioes") or (), "CT", achados=set(achados),
            coracao_cm3=cor)
        lote_t = L.tasks_depois_da_base(
            MD.MODO_AUTO, an.get("regioes") or (), cor, "CT",
            permitidas=permitidas, achados=achados, catalogo=cat)
        checar(u"  e as tasks do AUTO: %s" % (u", ".join(tasks) or u"so a base"),
               tuple(vig_t) == tuple(tasks), str(vig_t))
        checar(u"  e o lote pede as MESMAS que o vigia",
               tuple(lote_t) == tuple(vig_t), u"%s x %s" % (lote_t, vig_t))
    an = _medir(fn, {"coracao"})
    checar(u"o coracao do modelo sai em cm3 (180,0), pela conta do motor",
           an.get("coracao_cm3") == 180.0, str(an.get("coracao_cm3")))
    checar(u"  e o laudo diz o volume",
           any(u"coracao do modelo: 180.0 cm3" in l
               for l in an.get("laudo") or ()), str(an.get("laudo")))
    an = _medir(fn, {"cabeca"})
    checar(u"o crânio sem pescoco: o laudo diz por que e cranio",
           any(l.startswith(u"cranio:") for l in an.get("laudo") or ()),
           str(an.get("laudo")))
    checar(u"  e o pescoco medido volta junto (os niveis nao rodam)",
           isinstance(an.get("pescoco"), tuple) and an["pescoco"][0] is False,
           str(an.get("pescoco")))
    an = _medir(fn, {"pescoco"})
    checar(u"o pescoco medido volta junto, e os niveis rodam por ele",
           isinstance(an.get("pescoco"), tuple) and an["pescoco"][0] is True,
           str(an.get("pescoco")))
    checar(u"sem grade: nada e medido, e nada levanta",
           tuple(fn({}, None).get("regioes") or ()) == ()
           and fn({}, None).get("coracao_cm3") is None)

    import inspect
    src = inspect.getsource(TP.anatomia_da_base)
    alvo = u"regioes.add(CRANIO)"
    ns = dict(vars(TP))
    exec(compile(src.replace(alvo, u"regioes.add(CABECA_PESCOCO)"),
                 "<isca-cranio>", "exec"), ns)
    an_i = _medir(ns["anatomia_da_base"], {"cabeca"})
    checar(u"ISCA: com a regra de antes (todo encefalo e cabeca e pescoco), "
           u"o cranio sem pescoco sai `cabeca_pescoco` — a checagem reprova",
           alvo in src and tuple(an_i.get("regioes") or ()) != ("cranio",),
           str(an_i.get("regioes")))



def teste_a_ultima_task_do_lote_nao_perde_o_fim_do_log():
    secao(u"E1: a ultima task do lote nao perde o fim do log")
    import time as _time
    import engine as E

    def _ts(ref, t, **k):
        _time.sleep(1.5)
        E._log(k.get("jid"), u"TS %s Predicted in 12.3 s" % t)
        E._log(k.get("jid"), u"TS %s memoria: 9.0 GB livres no inicio, 2.0 no "
                             u"pico de uso (-7.0 GB com tudo o que rodou "
                             u"junto), 88%% da estacao no pior momento" % t)
        return {"liver": 1}

    def _com_drenador(drenar):
        real = E.drenar_log
        E.drenar_log = (lambda jid, esc, parar, **kw:
                        drenar(jid, esc, parar, intervalo=30.0))
        linhas = []
        try:
            res, _c = _uma_serie_com_passos([], run_ts=_ts, log=linhas,
                                            modo="auto")
        finally:
            E.drenar_log = real
        return res, linhas

    res, linhas = _com_drenador(E.drenar_log)
    checar(u"a serie terminou", not res.get("erro"), str(res.get("erro")))
    checar(u"o «Predicted in» da ultima task chegou ao log do lote",
           any(u"Predicted in" in l for l in linhas),
           u" / ".join(linhas[-6:])[:300])
    checar(u"  e a linha de memoria dela tambem",
           any(u"memoria:" in l and u"88% da estacao" in l for l in linhas))

    def _de_antes(jid, escrever, parar, a_cada_s=None, intervalo=3.0):
        mostradas = 0
        filtro = E.FiltroProgresso(a_cada_s)
        while not parar.is_set():
            ls = (E._job(jid) or {}).get("log") or []
            for ln in ls[mostradas:]:
                if filtro.passa(ln):
                    escrever(str(ln))
            mostradas = len(ls)
            parar.wait(intervalo)
    _r, linhas_i = _com_drenador(_de_antes)
    checar(u"ISCA: com o drenador de antes, o fim da ultima task some do log "
           u"(a checagem sabe reprovar)",
           not any(u"Predicted in" in l for l in linhas_i),
           u" / ".join(linhas_i[-4:])[:300])


def teste_o_clip_box_e_os_niveis_do_fast_no_caso():
    secao(u"E1: o clip-box e os niveis do FAST no caso")
    import numpy as np
    import SimpleITK as sitk
    import engine as E
    ref = sitk.GetImageFromArray(np.zeros((40, 60, 50), dtype=np.int16))
    ref.SetSpacing((1.0, 1.0, 3.0))
    g = np.zeros((40, 60, 50), bool)
    g[18:23, 5:15, 5:45] = True
    checar(u"a variante medida do FAST saiu com a Breast_OAR: nenhuma task "
           u"tem recorte medido no FAST",
           not any(E.entrada_do_recorte(t, modo="fast").get("medido")
                   for t in E.RECORTE_POR_TASK))
    _guarda_rec = dict(E.RECORTE_POR_TASK)
    E.RECORTE_POR_TASK["abdominal_muscles"] = dict(
        _guarda_rec["abdominal_muscles"],
        fast={"ancora": "torax", "eixos": "z", "margem_mm": 10.0,
              "medido": True, "numeros": {"criterio": "isca_da_bateria"}})
    rec = {"abdominal_muscles": {"eixos": "z", "porque": u"isca",
                                 "zyx": [0, 1, 0, 1, 0, 1]}}
    esc_f = L.escolha_da_serie({"modo": "fast"})
    var = E.entrada_do_recorte("abdominal_muscles", modo="fast")
    pr = L.processamento_do_caso(esc_f, "fast",
                                 tasks=["total_v3", "abdominal_muscles"],
                                 recortes=rec)
    cb = (pr.get("clip_box") or {}).get("abdominal_muscles") or {}
    checar(u"o clip-box do FAST diz MEDIDO (a variante do modo)",
           cb.get("medido") is True and cb.get("usado") is True, str(cb)[:200])
    checar(u"  e leva os numeros da medida (o ganho e o criterio)",
           bool(var.get("numeros")) and cb.get("numeros") == var["numeros"],
           str(cb.get("numeros"))[:160])
    import radai_records as RG
    checar(u"  e e a montagem do vigia (`radai_records.clip_box_do_caso`)",
           cb == RG.clip_box_do_caso(rec, modo="fast",
                                     entrada=E.entrada_do_recorte)
           ["abdominal_muscles"])
    import inspect
    src = inspect.getsource(L.processamento_do_caso)
    alvo = u"modo=origem, entrada=_entrada"
    ns = dict(vars(L))
    exec(compile(src.replace(alvo, u"modo=None, entrada=_entrada"),
                 "<isca-clip>", "exec"), ns)
    cb_i = ((ns["processamento_do_caso"](esc_f, "fast", recortes=rec)
             .get("clip_box") or {}).get("abdominal_muscles") or {})
    E.RECORTE_POR_TASK.clear()
    E.RECORTE_POR_TASK.update(_guarda_rec)
    checar(u"ISCA: pela entrada da TASK (a leitura de antes), o recorte do FAST "
           u"sai «nao medido» e sem numeros -- a checagem reprova",
           alvo in src and cb_i.get("medido") is False
           and not cb_i.get("numeros"), str(cb_i)[:160])

    _r, caso = _uma_serie_com_passos([], modo="fast")
    nc = (caso.get("processamento") or {}).get("niveis_cervicais") or {}
    checar(u"FAST: os niveis nao rodam, e o motivo DIZ que e o FAST",
           nc.get("rodam") is False and u"FAST" in (nc.get("motivo") or u""),
           str(nc))
    velho = dict(L.MOTIVO_DOS_NIVEIS_FORA_DO_MODO)
    try:
        L.MOTIVO_DOS_NIVEIS_FORA_DO_MODO.update({"fast": u"", "lista": u""})
        _r, caso_i = _uma_serie_com_passos([], modo="fast")
    finally:
        L.MOTIVO_DOS_NIVEIS_FORA_DO_MODO.clear()
        L.MOTIVO_DOS_NIVEIS_FORA_DO_MODO.update(velho)
    nc_i = (caso_i.get("processamento") or {}).get("niveis_cervicais") or {}
    checar(u"ISCA: sem o motivo do modo, o caso volta a `motivo: \"\"` (o da "
           u"prova) -- a checagem reprova", nc_i.get("motivo") == u"",
           str(nc_i))


def teste_o_caso_do_lote_leva_o_que_a_regiao_tirou():
    secao(u"E1: o caso do lote leva o que a regiao tirou do OAR")
    import radai_records as RG
    fora = {"pelvic_muscles": u"pelve nao identificada pela anatomia (pelve: "
                              u"nao (nenhum marco desenhado))"}
    pr = L.processamento_do_caso(L.escolha_da_serie({"modo": "auto"}), "auto",
                                 tasks=["total_v3"], oar_fora_por_regiao=fora)
    checar(u"o campo e do registro, no formato [{chave, motivo}]",
           "oar_fora_por_regiao" in RG.CAMPOS_DO_PROCESSAMENTO
           and pr.get("oar_fora_por_regiao")
           == [{"chave": "pelvic_muscles", "motivo": fora["pelvic_muscles"]}],
           str(pr.get("oar_fora_por_regiao")))
    checar(u"  e sem a porta ter respondido (`None`), fica FORA",
           "oar_fora_por_regiao" not in L.processamento_do_caso(
               {}, "auto", tasks=["total_v3"]))
    import inspect
    _res, caso = _uma_serie_com_passos([], modo="auto", fora_regiao=fora)
    checar(u"pela serie de verdade: o caso leva o que a regiao tirou",
           (caso.get("processamento") or {}).get("oar_fora_por_regiao")
           == [{"chave": "pelvic_muscles", "motivo": fora["pelvic_muscles"]}],
           str((caso.get("processamento") or {}).get("oar_fora_por_regiao")))
    src_u = inspect.getsource(L._uma_serie)
    alvo = u"oar_fora_por_regiao=_fora_por_regiao[0])"
    ns = dict(vars(L))
    exec(compile(src_u.replace(alvo, u"oar_fora_por_regiao=None)"),
                 "<isca-regiao>", "exec"), ns)
    _r, caso_i = _uma_serie_com_passos([], modo="auto", fora_regiao=fora,
                                       fn=ns["_uma_serie"])
    checar(u"ISCA: sem o campo na chamada, o caso sai sem ele (a checagem "
           u"reprova)", alvo in src_u and "oar_fora_por_regiao" not in (
               caso_i.get("processamento") or {}))


def teste_a_previa_diz_a_condicao_da_pelve():
    secao(u"E1: a previa diz a condicao da pelve")
    import engine as E
    exig = dict(getattr(E, "REGIAO_EXIGIDA_NO_OAR", {}) or {})
    checar(u"o motor declara o portao de regiao do OAR", bool(exig), str(exig))
    s = L._com_escolhas_da_tela({"series": [
        {"uid": "1.2.3.4.5.77", "modo": "auto", "modalidade": "CT"}]})[0]
    prev = L.previa_da_entrega(s)
    por = dict((e["chave"], e) for e in prev["oar"]["estruturas"])
    alvo = sorted(k for k in exig if k in por)
    checar(u"a previa do AUTO anuncia o composto da pelve (%s)"
           % u", ".join(alvo), bool(alvo), str(sorted(por))[:200])
    checar(u"  com a condicao «so com a pelve identificada» ao lado",
           alvo and all(por[k].get("condicao")
                        == L.CONDICAO_DA_REGIAO_NA_PREVIA["pelve"]
                        for k in alvo), str([por[k] for k in alvo])[:200])
    checar(u"  e nenhuma outra estrutura leva condicao",
           not [k for k, e in por.items() if e.get("condicao")
                and k not in exig
                and e.get("condicao") not in (L.CONDICAO_DO_ENCEFALO_NA_PREVIA,
                                              L.CONDICAO_DO_PESCOCO_NA_PREVIA)])
    tasks = list(prev["tasks"]) + list(prev["tasks_depois_da_base"])
    ests_t, _f = L.estruturas_do_oar_possiveis("auto", tasks, "CT",
                                               regioes=("torax",))
    ests_p, _f = L.estruturas_do_oar_possiveis("auto", tasks, "CT",
                                               regioes=("pelve",))
    ch_t = dict((e["chave"], e) for e in ests_t)
    ch_p = dict((e["chave"], e) for e in ests_p)
    checar(u"com as regioes medidas e SEM a pelve, o composto da pelve nao e "
           u"possivel", not (set(alvo) & set(ch_t)), str(sorted(ch_t))[:200])
    checar(u"  e com a pelve, e possivel e sem condicao",
           set(alvo) <= set(ch_p)
           and not any(ch_p[k].get("condicao") for k in alvo))
    velho = E.REGIAO_EXIGIDA_NO_OAR
    try:
        E.REGIAO_EXIGIDA_NO_OAR = {}
        prev_i = L.previa_da_entrega(s)
    finally:
        E.REGIAO_EXIGIDA_NO_OAR = velho
    checar(u"ISCA: sem o portao de regiao, a previa volta a anunciar sem "
           u"ressalva (a checagem reprova)",
           not any(e.get("condicao") for e in prev_i["oar"]["estruturas"]
                   if e.get("condicao") not in (
                       L.CONDICAO_DO_ENCEFALO_NA_PREVIA,
                       L.CONDICAO_DO_PESCOCO_NA_PREVIA)))
    import json as _json
    pag = L.PAGINA
    fontes = [_corpo_js(pag, n) for n in (u"esc", u"_condHTML", u"_tagHTML")]
    checar(u"as funcoes da tag estao na pagina", all(fontes))
    if not all(fontes):
        return
    it = {"chave": "pelvic_muscles", "nome": "Muscles_ai",
          "condicao": L.CONDICAO_DA_REGIAO_NA_PREVIA["pelve"]}
    js = (u"\n".join(fontes) + u"\nvar R = {com: _tagHTML(%s, false), "
          u"fora: _tagHTML(%s, true), sem: _tagHTML({chave:'liver', "
          u"nome:'Liver_ai'}, false)};\nconsole.log('JSON:' + "
          u"JSON.stringify(R));\n" % (_json.dumps(it), _json.dumps(it)))
    res, erro = _rodar_js_no_node(js, prefixo=u"radai_t_cond_")
    if erro.startswith(u"PULADO"):
        checar(u"`node` nesta maquina (PULADO: sem ele o JS nao roda aqui)",
               True)
        return
    frase = L.CONDICAO_DA_REGIAO_NA_PREVIA["pelve"]
    checar(u"o JS desenha a condicao DENTRO da tag, com a marca de traducao",
           res is not None and u'class="oar-cond" data-radai-frase' in res["com"]
           and frase in res["com"] and frase in res["fora"]
           and res["com"].index(u"Muscles_ai") < res["com"].index(frase),
           (erro or str(res))[:300])
    checar(u"  e a tag sem condicao nao ganha o span",
           res is not None and u"oar-cond" not in res["sem"])
    res_i, _e = _rodar_js_no_node(
        js.replace(u"</span>' + _condHTML(it)", u"</span>'"),
        prefixo=u"radai_t_cond_")
    checar(u"ISCA: o `_tagHTML` sem `_condHTML(it)` nao desenha a condicao "
           u"(a checagem reprova)",
           res_i is not None and frase not in res_i["com"], _e)


def teste_os_constritores_na_previa_so_com_o_pescoco():
    secao(u"a previa do PERSONALIZADO: os constritores so com o pescoco")
    import engine as E
    cons = ("pharyngeal_constrictor_inferior", "pharyngeal_constrictor_middle",
            "pharyngeal_constrictor_superior")
    tasks = ["trunk_cavities", "headneck_muscles"]
    checar(u"o motor trava a task dos constritores pelo pescoco",
           (getattr(E, "REGIAO_DA_TASK", {}) or {}).get("headneck_muscles")
           == L.REGIAO_DO_PESCOCO_NA_PREVIA)
    ests, _f = L.estruturas_do_oar_possiveis("perso", tasks, "CT")
    por = dict((e["chave"], e) for e in ests)
    checar(u"numa TC de torax com a task ligada a mao, a previa anuncia os "
           u"constritores com «so com o pescoco confirmado»",
           all(por.get(k, {}).get("condicao")
               == L.CONDICAO_DO_PESCOCO_NA_PREVIA for k in cons),
           str([por.get(k) for k in cons])[:300])
    checar(u"  e o que vem de task sem trava (o coracao) nao leva a condicao",
           "heart" in por and por["heart"].get("condicao")
           != L.CONDICAO_DO_PESCOCO_NA_PREVIA, str(por.get("heart")))
    e_t, _f = L.estruturas_do_oar_possiveis("perso", tasks, "CT",
                                            regioes=("torax",))
    checar(u"com as regioes medidas e SEM o pescoco, eles nao sao possiveis",
           not set(cons) & set(e["chave"] for e in e_t))
    e_p, _f = L.estruturas_do_oar_possiveis("perso", tasks, "CT",
                                            regioes=("torax", "cabeca_pescoco"))
    checar(u"  e com o pescoco medido, aparecem, ainda com a condicao (a trava "
           u"confere a mandibula tambem)",
           all(any(e["chave"] == k and e.get("condicao")
                   == L.CONDICAO_DO_PESCOCO_NA_PREVIA for e in e_p)
               for k in cons))
    velho = E.REGIAO_DA_TASK
    try:
        E.REGIAO_DA_TASK = dict((t, r) for t, r in velho.items()
                                if t != "headneck_muscles")
        e_i, _f = L.estruturas_do_oar_possiveis("perso", tasks, "CT")
    finally:
        E.REGIAO_DA_TASK = velho
    checar(u"ISCA: sem a trava do motor, a previa volta a anunciar os "
           u"constritores sem ressalva (a checagem sabe reprovar)",
           all(not e.get("condicao") for e in e_i if e["chave"] in cons)
           and set(cons) <= set(e["chave"] for e in e_i))


def teste_a_rm_sagital_nao_e_reconstrucao_impropria():
    secao(u"a lista: a RM sagital nao e «reconstrucao coronal ou sagital»")
    fontes = [_corpo_js(L.PAGINA, n) for n in (u"linhaDaSerie",
                                                u"modalidadeDe")]
    checar(u"as funcoes da linha estao na pagina", all(fontes))
    if not all(fontes):
        return
    frase = u"reconstrução coronal ou sagital"
    dubles = u"""
var SERIES = [], INCL = {}, PREV_ABERTA = {};
function esc(s){ return String(s == null ? '' : s) }
function dataBr(d){ return d } function horaBr(){ return '' }
function celulaModalidade(){ return '<td></td>' }
function celulaSerie(){ return '' } function celulaModo(){ return '' }
function chaveDe(s){ return s.uid }
var window = {};
"""
    roda = u"""
SERIES = [{uid: 'RM', modalidade: 'MR', axial: false, sugerida: true},
          {uid: 'TC', modalidade: 'CT', axial: false},
          {uid: 'SEM', modalidade: '', axial: false},
          {uid: 'AX', modalidade: 'CT', axial: true}];
var R = {};
SERIES.forEach(function(s, i){ R[s.uid] = linhaDaSerie(i) });
console.log('JSON:' + JSON.stringify(R));
"""
    js = dubles + u"\n".join(fontes) + roda
    res, erro = _rodar_js_no_node(js, prefixo=u"radai_t_sagital_")
    if erro.startswith(u"PULADO"):
        checar(u"`node` nesta maquina (PULADO: sem ele o JS nao roda aqui)",
               True)
        return
    checar(u"a linha executa no node", res is not None, erro[:200])
    if res is None:
        return
    checar(u"a RM sagital nao diz «reconstrucao coronal ou sagital» (ela e "
           u"segmentada), e mostra a sugestao", frase not in res["RM"]
           and u"melhor reconstrução deste exame" in res["RM"], res["RM"][:300])
    checar(u"  e a TC fora do axial continua dizendo, com ou sem a modalidade "
           u"no cabecalho", frase in res["TC"] and frase in res["SEM"])
    checar(u"  e a TC axial nao diz", frase not in res["AX"])
    js_i = js.replace(u"s.axial===false && modalidadeDe(s)!=='MR'",
                      u"s.axial===false")
    res_i, _e = _rodar_js_no_node(js_i, prefixo=u"radai_t_sagital_i_")
    checar(u"ISCA: com a regra de antes, a RM sagital volta a dizer "
           u"«reconstrucao coronal ou sagital» (a checagem sabe reprovar)",
           js_i != js and res_i is not None and frase in res_i["RM"])


def teste_o_tremor_e_o_da_casca():
    secao(u"o tremor do Rodar agora e o da casca (rola e da o foco)")
    pag = _sem_comentario_js(L.PAGINA)
    checar(u"a pagina nao tem mais um treme() proprio",
           u"function treme(" not in pag)
    checar(u"  e os dois chamadores usam o uiTremer",
           u"uiTremer(el('pasta'))" in pag and u"uiTremer(el('btrodar'))" in pag)
    tst = _corpo_js(L.PAGINA, u"_ovTestar")
    checar(u"a folha do Overnight Run com o ROOT vazio treme o campo ao abrir",
           u"_ovTremerRoot()" in tst and u"vazio: true" in tst
           and u"OV.tremerAoAbrir = !root;" in _corpo_js(L.PAGINA, u"_ovPreencher"),
           tst[:200])
    lig = _corpo_js(L.PAGINA, u"_ovLigar")
    checar(u"  e o Enter com o ROOT vazio treme de novo",
           u"_ovTremerRoot()" in lig.split(u"ev.key === 'Enter'")[1][:300]
           if u"ev.key === 'Enter'" in lig else False)
    checar(u"  pelo uiTremer da casca", u"window.uiTremer(r)"
           in _corpo_js(L.PAGINA, u"_ovTremerRoot"))


def teste_o_protocolo_3d_diz_o_que_vai_ao_rtstruct():
    secao(u"o protocolo 3D diz que o RTSTRUCT sai so com as colunas de RT")
    painel = _corpo_js(L.PAGINA, u"painelPerso")
    i = painel.find(u"p4-rt3d")
    checar(u"o painel do PERSONALIZADO tem a nota do protocolo 3D", i > 0)
    checar(u"  so com um protocolo 3D ligado",
           u"if(protocolos3dLigados(s, e).length)" in painel[max(0, i - 160):i])
    checar(u"  dizendo com todas as letras que o RTSTRUCT sai so com as "
           u"colunas de RT, e com a marca de traducao",
           u"o RTSTRUCT sai só com o que estiver ligado nas colunas de RT"
           in painel and u'role="note" data-radai-frase' in painel)
    lp = _corpo_js(L.PAGINA, u"ligarProtocolo3d")
    checar(u"  e o comportamento nao mudou: o protocolo 3D desliga as tasks "
           u"de RT", u"_soAsDele(s, e, [])" in lp, lp[:200])


def teste_o_pericardio_nasce_ligado_no_personalizado():
    secao(u"4b: o pericardio nasce ligado no PERSONALIZADO da TC")
    import json as _json
    import radai_modes as _md
    T_PER = _md.TASK_DO_PERICARDIO

    def _perso(mod="CT", chaves=None, prot=()):
        s = {"uid": "1.2.3.44445555", "pasta": "P", "curto": "44445555",
             "modalidade": mod, "modo": "perso", "protocolos": list(prot)}
        if chaves is not None:
            s["tasks"] = dict(chaves)
        return s
    log = []
    t_ct, o = L.tasks_iniciais(_perso(), None, log.append)
    checar(u"PERSONALIZADO numa TC, sem a chave no payload: a cavidade do "
           u"tronco RODA", T_PER in t_ct and o == "perso", str(t_ct))
    checar(u"  e o log nao fala em pericardio desligado",
           not any(u"SEM pericardio" in l for l in log), u" | ".join(log))
    log = []
    t_off, _o = L.tasks_iniciais(_perso(chaves={T_PER: 0}), None, log.append)
    checar(u"a chave em 0 tira a cavidade (e so ela)", T_PER not in t_off,
           str(t_off))
    checar(u"  e o log da serie diz que o Heart_ai sai SEM pericardio, por "
           u"ato, e que foi a mao",
           any(_md.FRASE_DO_PERICARDIO_DESLIGADO % _md.QUEM_DESLIGOU_A_MAO
               in l for l in log), u" | ".join(log))
    log = []
    L.tasks_iniciais(_perso(chaves={T_PER: 0}, prot=("cranio",)), None,
                     log.append)
    _per = [l for l in log if u"SEM pericardio" in l]
    checar(u"  com o protocolo que nao a arrasta (Cranio), o log diz que foi o "
           u"protocolo, e nao a mao",
           _per and u"pelo protocolo «Crânio»" in _per[0]
           and u"DESLIGADA a mao" not in _per[0], u" | ".join(_per))
    s3d = _perso(chaves={T_PER: 0})
    s3d["protocolos_3d"] = ["anatomia_geral"]
    log = []
    L.tasks_iniciais(s3d, None, log.append)
    _per = [l for l in log if u"SEM pericardio" in l]
    checar(u"  com um protocolo das Reconstrucoes 3D, o log diz qual",
           _per and u"Reconstrucoes 3D «Anatomia Geral»" in _per[0], u" | ".join(_per))
    log = []
    L.tasks_iniciais(_perso(chaves={T_PER: 0}, prot=("torax_mama",)), None,
                     log.append)
    _per = [l for l in log if u"SEM pericardio" in l]
    checar(u"  com o protocolo que a arrasta e a chave em 0, foi a mao",
           _per and u"DESLIGADA a mao" in _per[0], u" | ".join(_per))
    checar(u"  (isca) a frase de antes, fixa em «a mao», nao diria o protocolo",
           u"pelo protocolo" not in (_md.FRASE_DO_PERICARDIO_DESLIGADO
                                     % _md.QUEM_DESLIGOU_A_MAO))
    t_mr, _o = L.tasks_iniciais(_perso("MR"), None, None)
    checar(u"na RM nada muda (a cavidade e modelo de TC)",
           T_PER not in t_mr, str(t_mr))
    checar(u"as opcoes da tela levam a tabela de fabrica (TC sim, RM nao)",
           L.opcoes_da_tela("CT").get("ligadas_de_fabrica")
           == [T_PER, "pleural_pericard_effusion"]
           and L.opcoes_da_tela("MR").get("ligadas_de_fabrica") == [],
           str(L.opcoes_da_tela("CT").get("ligadas_de_fabrica")))

    def _heart(prev):
        for it in (prev.get("oar") or {}).get("estruturas") or ():
            if it.get("chave") == L.CHAVE_DO_HEART_AI_NA_PREVIA:
                return it
        return {}
    V = L.VARIANTE_DO_HEART_AI_NA_PREVIA
    import radai_constructs as _rcs
    checar(u"a chave do Heart_ai na previa e a do motor "
           u"(`radai_constructs.CHAVE_CORACAO_AI`)",
           L.CHAVE_DO_HEART_AI_NA_PREVIA == _rcs.CHAVE_CORACAO_AI)
    h_on = _heart(L.previa_da_entrega(_perso()))
    h_off = _heart(L.previa_da_entrega(_perso(chaves={T_PER: 0})))
    h_mr = _heart(L.previa_da_entrega(_perso("MR")))
    h_auto = _heart(L.previa_da_entrega({"uid": "1.2.3.44445555",
                                         "pasta": "P", "modalidade": "CT",
                                         "modo": "auto"}))
    h_fast = _heart(L.previa_da_entrega({"uid": "1.2.3.44445555",
                                         "pasta": "P", "modalidade": "CT",
                                         "modo": "fast"}))
    checar(u"a previa: Heart_ai «com pericardio» com a chave ligada",
           h_on.get("pericardio") is True and h_on.get("variante") == V["com"],
           str(h_on))
    checar(u"  e «sem pericardio» com a chave em 0",
           h_off.get("pericardio") is False
           and h_off.get("variante") == V["desligada"], str(h_off))
    checar(u"  e na RM, sem (a cavidade nao roda ali)",
           h_mr.get("pericardio") is False and h_mr.get("variante") == V["rm"],
           str(h_mr))
    checar(u"  e no AUTO e no FAST da TC, com (os dois pedem a cavidade "
           u"quando o coracao sai)", h_auto.get("pericardio") is True
           and h_fast.get("pericardio") is True, str((h_auto, h_fast)))
    _velha = _md.LIGADAS_DE_FABRICA_NO_PERSO
    try:
        _md.LIGADAS_DE_FABRICA_NO_PERSO = {}
        t_isca, _o = L.tasks_iniciais(_perso(), None, None)
        h_isca = _heart(L.previa_da_entrega(_perso()))
    finally:
        _md.LIGADAS_DE_FABRICA_NO_PERSO = _velha
    checar(u"  (isca) sem a tabela de fabrica, a serie roda so a base e a "
           u"previa diz «sem» -- a checagem discrimina",
           T_PER not in t_isca and h_isca.get("pericardio") is False,
           u"%s | %s" % (t_isca, h_isca))

    pag = L.PAGINA
    nomes = (u"_porTask", u"_arrastavel", u"tasksLigadas", u"chaveDaTask",
             u"ligarSelecaoLivre", u"chavesFinais", u"_ppsDaSerie",
             u"_ppDaSerie", u"_travadasPeloPp")
    fontes = [_corpo_js(pag, n) for n in nomes]
    checar(u"as funcoes das chaves estao na pagina", all(fontes))
    if not all(fontes):
        return
    roda = (u"\nvar R = {};\nvar e = E();\nR.nasce = Object.keys("
            u"tasksLigadas(S, e));\nchaveDaTask(S, e, '%s', false);\n"
            u"R.desligada = Object.keys(tasksLigadas(S, e));\n"
            u"R.finais = chavesFinais(S, e);\n"
            u"console.log('JSON:' + JSON.stringify(R));\n" % T_PER)
    js = (_CHAVES_DUBLES_JS % {"opc": _json.dumps(L.opcoes_da_tela("CT"),
                                                  default=str)}
          + u"\n".join(fontes) + roda)
    res, erro = _rodar_js_no_node(js, prefixo=u"radai_t_peri_")
    if erro.startswith(u"PULADO"):
        checar(u"`node` nesta maquina (PULADO: sem ele o JS nao roda aqui)",
               True)
        return
    checar(u"na tela, a chave da cavidade NASCE ligada (sem ninguem mexer)",
           res is not None and T_PER in res["nasce"],
           (erro or str(res))[:300])
    checar(u"  e desligada a mao, sai, e o estado final a leva em 0",
           res is not None and T_PER not in res["desligada"]
           and res["finais"].get(T_PER) == 0, str(res)[:300])
    linha = u"(d.ligadas_de_fabrica || []).forEach("
    r_isca, _e = _rodar_js_no_node(js.replace(linha, u"[].forEach("),
                                   prefixo=u"radai_t_peri_")
    checar(u"  (isca) `tasksLigadas` sem a tabela de fabrica: a chave aparece "
           u"desligada -- a checagem discrimina", linha in js
           and r_isca is not None and T_PER not in r_isca["nasce"], _e)
    js_mr = (_CHAVES_DUBLES_JS % {"opc": _json.dumps(L.opcoes_da_tela("MR"),
                                                     default=str)}
             + u"\n".join(fontes) + roda)
    r_mr, _e2 = _rodar_js_no_node(js_mr, prefixo=u"radai_t_peri_")
    checar(u"  e na RM a tela nao liga nada", r_mr is not None
           and r_mr["nasce"] == [], str(r_mr)[:200])

    fts = [_corpo_js(pag, n) for n in (u"esc", u"_condHTML", u"_tagHTML")]
    js_t = (u"\n".join(fts) + u"\nvar R = {com: _tagHTML(%s, false), "
            u"sem: _tagHTML(%s, false), fora: _tagHTML(%s, true)};\n"
            u"console.log('JSON:' + JSON.stringify(R));\n"
            % (_json.dumps(h_on), _json.dumps(h_off), _json.dumps(h_off)))
    r_t, e_t = _rodar_js_no_node(js_t, prefixo=u"radai_t_peri_")
    checar(u"a tag do Heart_ai diz «com pericardio» ou «sem», com a marca de "
           u"traducao", r_t is not None and V["com"] in r_t["com"]
           and V["desligada"] in r_t["sem"] and V["desligada"] in r_t["fora"]
           and u"data-radai-frase>%s<" % V["desligada"] in r_t["sem"],
           (e_t or str(r_t))[:300])
    checar(u"  e a de «sem» leva a classe que a destaca",
           r_t is not None and u"oar-var sem" in r_t["sem"]
           and u"oar-var sem" not in r_t["com"], str(r_t)[:300])
    r_ti, _e3 = _rodar_js_no_node(js_t.replace(u"it.variante ?", u"false ?"),
                                  prefixo=u"radai_t_peri_")
    checar(u"  (isca) a tag sem a variante nao diz nada -- a checagem "
           u"discrimina", u"it.variante ?" in js_t and r_ti is not None
           and V["desligada"] not in r_ti["sem"], _e3)


_TURNO_DUBLES_JS = u"""
var CAP = {urls: [], card: [], recarregou: 0};
var PACOTE = null, RESP = {};
var OV = {turno: false, pendente: false};
function filaOvernight(){ return Promise.resolve(PACOTE) }
function fetch(u, o){ CAP.urls.push(u); var r = RESP[u] || {ok: true};
  return Promise.resolve({json: function(){ return Promise.resolve(r) }}) }
function _ovCard(t){ CAP.card.push(t) }
function _ovTextoAberto(){ return 'ABERTO' }
function radaiFilaCarregar(){ CAP.recarregou++ }
"""

_TURNO_RODA_JS = u"""
var CEN = %(cen)s;
async function roda(){
 var R = {};
 for(var k = 0; k < CEN.length; k++){
  var c = CEN[k];
  CAP = {urls: [], card: [], recarregou: 0}; PACOTE = c.pacote; RESP = c.resp || {};
  var erro = null;
  try{ await _ovPorNaFila(true, null) }catch(e){ erro = String((e && e.message) || e) }
  R[c.nome] = {urls: CAP.urls, card: CAP.card, erro: erro, recarregou: CAP.recarregou};
 }
 console.log('JSON:' + JSON.stringify(R));
}
roda();
"""


def teste_o_turno_aguarda_iniciar():
    secao(u"o turno aguarda INICIAR, qualquer que seja a fila")
    import json as _json
    pag = L.PAGINA
    nomes = (u"_ovPorNaFila",)
    fontes = [_corpo_js(pag, n) for n in nomes]
    checar(u"as funcoes do modal do turno estao na pagina", all(fontes),
           str([bool(f) for f in fontes]))
    if not all(fontes):
        return
    serie = {"tipo": "serie", "estado": "esperando"}
    turno = {"tipo": "overnight", "estado": "esperando"}
    cen = [
        {"nome": "parada", "pacote": {"cards": [serie, turno],
                                      "lote": {"rodando": False,
                                               "pausa_pedida": False}}},
        {"nome": "andando", "pacote": {"cards": [dict(serie, estado="rodando"),
                                                 turno],
                                       "lote": {"rodando": True,
                                                "pausa_pedida": False}}},
        {"nome": "pausada", "pacote": {"cards": [dict(serie, estado="rodando"),
                                                 serie, turno],
                                       "lote": {"rodando": True,
                                                "pausa_pedida": True}},
         "resp": {"/api/pipeline/iniciar": {
             "ok": False,
             "erro": u"ja ha um processamento rodando nesta estacao"}}},
        {"nome": "vazia", "pacote": {"cards": [turno],
                                     "lote": {"rodando": False}}},
        {"nome": "recusa", "pacote": {"cards": [serie, turno],
                                      "lote": {"rodando": False}},
         "resp": {"/api/pipeline/iniciar": {
             "ok": False, "erro": u"o vigia esta segmentando"}}},
    ]
    js = (_TURNO_DUBLES_JS + u"\n".join(fontes)
          + _TURNO_RODA_JS % {"cen": _json.dumps(cen)})
    res, erro = _rodar_js_no_node(js, prefixo=u"radai_t_turno_")
    if erro.startswith(u"PULADO"):
        checar(u"`node` nesta maquina (PULADO: sem ele o JS nao roda aqui)",
               True)
        return
    checar(u"o modal do turno executa no node", res is not None, erro)
    if res is None:
        return
    for nome in ("parada", "andando", "pausada", "vazia", "recusa"):
        r = res[nome]
        checar(u"fila %s: incluir não dispara processamento e pede INICIAR" % nome,
               r["urls"] == [] and r["erro"] is None
               and any(u"aguardando INICIAR" in t for t in r["card"]), str(r))
    linha = u"_ovCard('Na fila, aguardando INICIAR.');"
    isca = js.replace(linha, u"fetch('/api/pipeline/iniciar', {method:'POST'});" + linha)
    r_i, e_i = _rodar_js_no_node(isca, prefixo=u"radai_t_turno_")
    checar(u"isca: o início automático indevido é detectado",
           linha in js and r_i is not None
           and r_i["parada"]["urls"] == [u"/api/pipeline/iniciar"], e_i)
    ov = _corpo_js(pag, u"ovIniciar")
    fo = _corpo_js(pag, u"folhaOvernight")
    checar(u"«Salvar e incluir na fila» passa por `ovIniciar`, que chama `_ovPorNaFila`",
           u"_ovPorNaFila(" in ov and u"ovIniciar(true" in fo
           and u"ovIniciar(false" not in pag, u"")


def teste_a_data_do_nome_e_uma_regra_so():
    secao(u"E1: a data do nome e uma regra so nas duas portas")
    import radai_sets as RS
    dn = RS.data_do_nome
    checar(u"a data do DICOM entra no nome (8 digitos)",
           dn({"date": "20260927103000"}) == "20260927")
    checar(u"  a data que veio da PASTA nao entra: `semdata`",
           dn({"date": "20260927103000", "data_da_pasta": True})
           == RS.SEM_DATA)
    checar(u"  sem data, `semdata`; e o zero de reserva do vigia tambem",
           dn({"date": ""}) == RS.SEM_DATA
           and dn({"date": "00000000000000"}) == RS.SEM_DATA
           and dn({}) == RS.SEM_DATA and dn(None) == RS.SEM_DATA)
    _antes = lambda s: (s.get("date") or "")[:8] or RS.SEM_DATA
    checar(u"ISCA: pela regra de antes, a data da pasta entra no nome (a "
           u"checagem reprova)",
           _antes({"date": "20260927103000", "data_da_pasta": True})
           != RS.SEM_DATA)
    import pydicom
    base = tempfile.mkdtemp(prefix="radai_t_datanome_")
    try:
        from datetime import datetime as _dt
        sys.path.insert(0, AQUI)
        from make_test_series import escreve_serie
        pasta = os.path.join(base, "PAC_DATA")
        escreve_serie(pasta, "PAC_DATA", _dt(2026, 9, 20), 6)
        for f in os.listdir(pasta):
            fp = os.path.join(pasta, f)
            ds = pydicom.dcmread(fp)
            del ds.SeriesDate
            ds.save_as(fp)
        ss = L.varrer(pasta, min_cortes=3)
        checar(u"o lote le a data do ESTUDO numa serie sem a da serie (a "
               u"ordem do vigia)", ss and ss[0].get("date") == "20260920",
               str([x.get("date") for x in ss]))
        arq = L.arquivos_da_escolha(dict(ss[0], modo="auto")) if ss else []
        checar(u"  e a previa nomeia o arquivo com ela",
               arq and all(u"_20260920_" in a["arquivo"] for a in arq),
               str([a["arquivo"] for a in arq]))
        for f in os.listdir(pasta):
            fp = os.path.join(pasta, f)
            ds = pydicom.dcmread(fp)
            del ds.StudyDate
            ds.save_as(fp)
        ss = L.varrer(pasta, min_cortes=3)
        arq = L.arquivos_da_escolha(dict(ss[0], modo="auto")) if ss else []
        checar(u"  e sem data nenhuma, `semdata` no nome",
               arq and all(u"_semdata_" in a["arquivo"] for a in arq),
               str([a["arquivo"] for a in arq]))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def teste_o_marcador_so_com_rtstruct_no_disco():
    secao(u"o marcador de pronta so com RTSTRUCT RadAI gravado e conferido")
    import ast
    import tempfile as _tf

    class _Sd(object):
        def __init__(self, destino, gravados):
            self.destino, self.rs_name = destino, "RS_RadAI_20261015_abcd1234.dcm"
            self.gravados = list(gravados)

        def _alvo(self, infixo):
            return _ALVO_DE_VERDADE(self, infixo)
    d = _tf.mkdtemp(prefix="radai_lote_rs_")
    try:
        sd = _Sd(d, ["oar", "full"])
        io.open(sd._alvo(""), "wb").write(b"RT")
        conf, faltam = L.rtstruct_no_disco(sd)
        checar(u"o OAR no disco conta; o FULL anunciado e ausente fica de fora",
               conf == ["oar"] and faltam == ["full"], "%s %s" % (conf, faltam))
        vazio = _Sd(d, ["full"])
        try:
            L.exigir_rtstruct_no_disco(vazio, u"o FULL nao coube na memoria")
            recusou, msg = False, u""
        except RuntimeError as e:
            recusou, msg = True, u"%s" % e
        checar(u"sem nenhum RTSTRUCT no disco: falha, com o motivo (o que foi "
               u"anunciado e o que a entrega disse)",
               recusou and u"nao e marcada pronta" in msg.lower()
               and u"full" in msg and u"memoria" in msg, msg)
        zero = _Sd(d, ["fast"])
        io.open(zero._alvo("FAST_"), "wb").close()
        checar(u"  o arquivo de 0 byte nao conta como gravado",
               L.rtstruct_no_disco(zero)[0] == [])
        checar(u"  (isca) a lista do que a Saida diz ter gravado, sozinha, "
               u"daria pronta sem arquivo", bool(vazio.gravados))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    fonte = io.open(_componentes.fonte("app/radai_batch.py"),
                    encoding="utf-8").read()
    fn = [n for n in ast.walk(ast.parse(fonte))
          if isinstance(n, ast.FunctionDef) and n.name == "_uma_serie"]
    linhas = {"exigir": None, "entregou": None, "done": None}
    for n in ast.walk(fn[0]) if fn else ():
        if isinstance(n, ast.Call):
            nome = getattr(n.func, "id", None) or getattr(n.func, "attr", "")
            if nome == "exigir_rtstruct_no_disco":
                linhas["exigir"] = n.lineno
            elif nome == "_marcar_done" and linhas["done"] is None:
                linhas["done"] = n.lineno
        if (isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Subscript)
                and getattr(n.targets[0].value, "id", "") == "_subst"
                and getattr(n.value, "value", None) is True):
            linhas["entregou"] = n.lineno
    checar(u"no lote, a conferencia vem ANTES de dar a entrega por feita e "
           u"antes do marcador",
           None not in linhas.values()
           and linhas["exigir"] < linhas["entregou"] < linhas["done"],
           str(linhas))


def teste_a_previa_e_as_estruturas_novas_do_oar():
    secao(u"a previa do PERSONALIZADO: as cristas iliacas, o anus e nenhuma "
          u"exigencia morta")
    import engine as _E
    import radai_sets as _rs
    vivas = set(_rs.PERMITIDOS_NO_OAR) | set(
        getattr(_rs, "PERMITIDOS_NO_OAR_FAST", ()) or ())
    mortas = [k for k in L.EXIGENCIAS_NA_PREVIA if k not in vivas]
    checar(u"toda exigencia da previa e de uma estrutura que o OAR leva "
           u"(nenhuma chave que ninguem le)", not mortas, str(mortas))
    isca = dict(L.EXIGENCIAS_NA_PREVIA)
    isca["pleural_effusion_left"] = {"tasks": ("pleural_pericard_effusion",)}
    checar(u"  (isca) o derrame, que so vai ao FULL, seria acusado",
           [k for k in isca if k not in vivas] == ["pleural_effusion_left"])
    novas = [k for k in ("iliac_crest_left", "iliac_crest_right", "anus")
             if k in _rs.PERMITIDOS_NO_OAR]
    if len(novas) < 3:
        print(u"  pendente (MOTOR): as cristas e o anus ainda nao estao no "
              u"OAR (%s)" % novas)
        return
    nomes = dict((k, _E.nome_clinico(k)) for k in novas)
    checar(u"os nomes do TPS: IliacCrest_L_ai, IliacCrest_R_ai e Anus_ai "
           u"(ate 16 caracteres)",
           nomes == {"iliac_crest_left": u"IliacCrest_L_ai",
                     "iliac_crest_right": u"IliacCrest_R_ai",
                     "anus": u"Anus_ai"}
           and all(len(v) <= 16 for v in nomes.values()), str(nomes))
    com, _f = L.estruturas_do_oar_possiveis("perso", ["trunk_cavities"], "CT")
    por = dict((e["chave"], e) for e in com)
    checar(u"PERSONALIZADO com a cavidade do tronco: as tres aparecem, como "
           u"construcao, com o nome do TPS",
           all(k in por and por[k]["construcao"]
               and por[k]["nome"] == nomes[k] for k in novas),
           str([por.get(k) for k in novas]))
    sem, _f = L.estruturas_do_oar_possiveis("perso", [], "CT")
    sem_k = set(e["chave"] for e in sem)
    checar(u"  sem a cavidade do tronco o anus nao e anunciado (ele exige a "
           u"cavidade abdominal) e as cristas sim (so pedem o quadril)",
           "anus" not in sem_k and "iliac_crest_left" in sem_k
           and "iliac_crest_right" in sem_k, str(sorted(sem_k & set(novas))))
    reg = dict(getattr(_E, "REGIAO_EXIGIDA_NO_OAR", {}) or {})
    sem_reg, _f = L.estruturas_do_oar_possiveis(
        "perso", ["trunk_cavities"], "CT", regioes=["torax"])
    sem_reg_k = set(e["chave"] for e in sem_reg)
    coerente = all((k not in sem_reg_k) if reg.get(k) == "pelve"
                   else (k in sem_reg_k) for k in novas)
    condicao = all(bool(por[k].get("condicao")) == bool(reg.get(k))
                   for k in novas)
    checar(u"  e a regiao exigida pelo motor (REGIAO_EXIGIDA_NO_OAR) vale para "
           u"elas na previa: a condicao quando a regiao nao foi medida, e a "
           u"saida quando ela nao esta", coerente and condicao,
           u"regiao=%s, com tórax=%s" % (dict((k, reg.get(k)) for k in novas),
                                         sorted(sem_reg_k & set(novas))))
    todas = set(e["chave"] for e in com) | set(e["nome"] for e in com)
    checar(u"  e nenhuma Breast_OAR", not [x for x in todas
                                          if u"breast_oar" in x.lower()],
           str(sorted(todas))[:200])


def main():
    print("test_batch | entrada do caso: .zip do portal e escolha da serie")
    for t in (teste_zip_extrai_o_que_e_imagem,
              teste_zip_nao_funde_as_series,
              teste_apontar_a_pasta_acha_o_exame_empacotado,
              teste_espiar_nao_escreve_nada,
              teste_zip_ilegivel_nao_derruba_a_pasta,
              teste_zip_diz_o_motivo_em_portugues,
              teste_zip_extrai_uma_vez_so,
              teste_extracao_sobrevive_ao_reinicio,
              teste_nao_extrai_exame_para_dentro_do_programa,
              teste_zip_com_caminho_para_fora_e_ignorado,
              teste_a_serie_sugerida_e_a_que_serve,
              teste_numero_do_dicom_nao_explode,
              teste_uma_serie_nao_processa_sem_coordenacao,
              teste_uma_serie_usa_a_config_do_lote,
              teste_o_tx_sai_pelos_dois_caminhos,
              teste_a_serie_nao_ganha_tx_em_disco,
              teste_falha_de_ambiente_nao_vira_falha_de_serie,
              teste_o_erro_da_serie_chega_na_tela,
              teste_fila_de_casos,
              teste_os_dois_caminhos_gravam_os_mesmos_conjuntos,
              teste_o_localizar_filtra_a_lista,
              teste_o_carrinho_atravessa_a_troca_de_pasta,
              teste_a_tabela_agrupa_por_estudo,
              teste_os_tres_cards_e_o_turno_da_noite,
              teste_o_cads_roda_no_rodar_agora,
              teste_o_nome_do_paciente_aparece_na_tela_e_so_nela,
              teste_lock_morto_nao_trava_a_serie_para_sempre,
              teste_o_dropdown_do_rodar_agora_executa_a_trava_das_categorias,
              teste_o_nv_nao_liga_por_omissao_em_caminho_nenhum,
              teste_o_modo_da_tela_decide_e_nao_a_lista_do_config,
              teste_serie_zipada_grava_em_caminho_absoluto,
              teste_a_coluna_de_modalidade_roteia_os_plugins_da_linha,
              teste_o_modo_e_da_serie_e_chega_ao_motor,
              teste_os_niveis_cervicais_saem_pelo_rodar_agora,
              teste_o_explorador_do_passo_1,
              teste_o_otimizar_saiu_do_lote,
              teste_o_andamento_vai_para_o_card_que_roda,
              teste_a_conferencia_soma_os_modos_das_series,
              teste_a_regua_de_cpu_tem_uma_fonte_so,
              teste_a_ficha_diz_o_recorte_da_estacao,
              teste_a_conferencia_diz_o_que_nao_calculou,
              teste_a_modalidade_e_o_registro_saem_da_serie,
              teste_a_rm_sem_modo_nao_roda_a_base_de_tc,
              teste_o_erro_do_zip_nao_leva_o_paciente_ao_log,
              teste_o_explorador_nao_devolve_o_caminho_no_erro,
              teste_a_fila_que_nao_se_le_nao_e_vazia,
              teste_o_batimento_do_lote_olha_o_que_renovar_devolve,
              teste_a_varredura_nao_sugere_topografia_por_texto,
              teste_pedir_de_novo_leva_os_estudos_junto,
              teste_a_primeira_entrega_vale_no_lote,
              teste_o_selo_do_motor_diz_de_onde_vem,
              teste_o_lote_extrai_o_zip_pela_conta_do_acervo,
              teste_a_extracao_do_zip_fica_em_uso_ate_o_lote_acabar,
              teste_os_passos_do_full_chegam_ao_caso_do_lote,
              teste_o_corte_do_detalhe_do_zip,
              teste_a_task_marcada_que_falha_nao_derruba_a_serie,
              teste_a_previa_bate_com_o_que_a_execucao_grava,
              teste_a_parotida_do_viii_e_uma_linha_so_na_previa,
              teste_a_task_travada_vai_para_o_fim,
              teste_o_falhou_do_lote_nao_leva_caminho_nem_uid,
              teste_a_espessura_e_medida_na_normal_do_corte,
              teste_o_caso_leva_o_processamento_da_v83,
              teste_a_serie_do_lote_manda_o_toast_do_windows,
              teste_as_chaves_da_tela_e_o_servidor_concordam,
              teste_a_linha_da_serie_e_o_modal_do_turno_da_v83,
              teste_a_anatomia_da_base_e_uma_so_nas_duas_portas,
              teste_a_ultima_task_do_lote_nao_perde_o_fim_do_log,
              teste_o_clip_box_e_os_niveis_do_fast_no_caso,
              teste_o_caso_do_lote_leva_o_que_a_regiao_tirou,
              teste_a_previa_diz_a_condicao_da_pelve,
              teste_os_constritores_na_previa_so_com_o_pescoco,
              teste_a_rm_sagital_nao_e_reconstrucao_impropria,
              teste_o_tremor_e_o_da_casca,
              teste_o_protocolo_3d_diz_o_que_vai_ao_rtstruct,
              teste_a_data_do_nome_e_uma_regra_so,
              teste_o_pericardio_nasce_ligado_no_personalizado,
              teste_o_turno_aguarda_iniciar,
              teste_rodar_agora_nao_apaga_a_entrega_de_outra_serie_da_pasta,
              teste_substituir_refaz_a_serie_concluida,
              teste_a_linha_cabe_e_fala_com_o_leitor_de_tela,
              teste_o_registro_de_casos_fica_isolado,
              teste_o_marcador_so_com_rtstruct_no_disco,
              teste_a_previa_e_as_estruturas_novas_do_oar):
        try:
            t()
        except Exception as e:
            import traceback
            checar("%s (excecao inesperada)" % t.__name__, False,
                   "%s: %s" % (type(e).__name__, e))
            traceback.print_exc()
    print()
    if FALHAS:
        print("FALHOU: %d de %d checagens" % (FALHAS, OK + FALHAS))
        return 1
    print("OK: %d checagens, todas passaram" % OK)
    return 0


if __name__ == "__main__":
    sys.exit(main())
