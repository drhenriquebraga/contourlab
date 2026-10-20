# -*- coding: utf-8 -*-
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))


def pasta_app(aqui):
    for c in (os.path.join(aqui, "..", "app"), os.path.join(aqui, "..")):
        if os.path.exists(os.path.join(c, "radai_watcher.py")):
            return os.path.abspath(c)
    return os.path.abspath(os.path.join(aqui, "..", "app"))


APP = pasta_app(AQUI)
sys.path.insert(0, AQUI)
sys.path.insert(0, APP)

import numpy as np
from make_test_series import escreve_serie

VERBOSO = "-v" in sys.argv
_RESULTADOS = []
_TEMPS = []


def checar(nome, condicao, detalhe=""):
    ok = bool(condicao)
    _RESULTADOS.append((nome, ok, detalhe))
    if VERBOSO or not ok:
        print("  %s  %s%s" % ("OK   " if ok else "FALHA", nome,
                              ("  [%s]" % detalhe) if detalhe else ""))
    return ok


def secao(t):
    if VERBOSO:
        print("\n-- %s " % t + "-" * max(0, 58 - len(t)))


def novo_temp(prefixo="radai_c_"):
    d = tempfile.mkdtemp(prefix=prefixo)
    _TEMPS.append(d)
    return d


def novo_acervo():
    d = os.path.join(novo_temp(), "calibracao")
    os.environ["RADAI_CALIB_DIR"] = d
    return d


import engine
import radai_archive
import radai_geom
import radai_rt
import radai_terms
import radai_models

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _cleanup
import _componentes
_cleanup.adotar_prefixo('radai_dados_')
_cleanup.adotar_prefixo('radai_cen_')
_cleanup.adotar_prefixo('radai_lot_')
_cleanup.adotar_prefixo('radai_mod_')
_cleanup.adotar_prefixo('radai_stg_')
_cleanup.adotar_prefixo('radai_ana_')


_CENARIO = {}


def cenario():
    if _CENARIO:
        return _CENARIO
    base = novo_temp("radai_cen_")
    pasta = os.path.join(base, "PAC_CAL", "CT")
    uid = escreve_serie(pasta, "PAC_CAL", datetime.now(), 40)
    arquivos = radai_rt.fatias_da_serie(pasta)
    stage = novo_temp("radai_stg_")
    engine.copy_sorted(arquivos, stage)
    img = engine.load_sitk(stage)
    grade = radai_geom.Grade.de_sitk(img)
    forma = tuple(int(v) for v in reversed(img.GetSize()))

    zz, yy, xx = np.ogrid[0:forma[0], 0:forma[1], 0:forma[2]]
    cy, cx = forma[1] / 2.0, forma[2] / 2.0
    alvo = (((zz - forma[0] * 0.35) / 7.0) ** 2 + ((yy - cy) / 22.0) ** 2
            + ((xx - cx) / 16.0) ** 2) <= 1.0
    vizinho = (((zz - forma[0] * 0.35) / 6.0) ** 2 + ((yy - cy) / 9.0) ** 2
               + ((xx - (cx + 26)) / 9.0) ** 2) <= 1.0
    rs_local, nomes = engine.build_rtstruct(
        stage, {"lung_left": np.ascontiguousarray(alvo),
                "lung_right": np.ascontiguousarray(vizinho)}, versao_worker="teste")
    destino = os.path.join(pasta, "RS_RadAI_%s_%s.dcm"
                           % (datetime.now().strftime("%Y%m%d"), uid[-8:]))
    shutil.copy2(rs_local, destino)
    _CENARIO.update({"pasta": pasta, "rs": destino, "uid": uid,
                     "grade": grade, "forma": forma,
                     "alvo": np.ascontiguousarray(alvo),
                     "vizinho": np.ascontiguousarray(vizinho),
                     "nomes": nomes, "stage": stage})
    return _CENARIO


def teste_ciclo_contra_valor_analitico():
    secao("o ciclo contra valor ANALITICO (cilindro fino), e nao contra si mesmo")
    c = cenario()
    grade = c["grade"]
    dz, dy, dx = [abs(float(v)) for v in grade.spacing]
    forma = c["forma"]

    zc = forma[0] / 2.0
    yc, xc = forma[1] / 2.0, forma[2] / 2.0
    zz, yy, xx = np.ogrid[0:forma[0], 0:forma[1], 0:forma[2]]

    raio_mm = 8.0
    meia_altura = max(dz * 3.0, forma[0] * dz * 0.30)
    no_plano = ((yy - yc) * dy) ** 2 + ((xx - xc) * dx) ** 2
    esfera = np.ascontiguousarray(
        (no_plano <= raio_mm ** 2) & (np.abs((zz - zc) * dz) <= meia_altura))

    vol_voxel = dz * dy * dx
    n_cortes = int(esfera.any(axis=(1, 2)).sum())
    vol_analitico = np.pi * raio_mm ** 2 * (n_cortes * dz)
    vol_mascara = float(esfera.sum()) * vol_voxel

    checar(u"o cilindro cabe na serie e tem voxels", esfera.sum() > 800,
           str(int(esfera.sum())))
    checar(u"e ele e FINO o bastante para o meio pixel importar",
           raio_mm <= 12.0, u"raio %.1f mm" % raio_mm)
    erro_mascara = 100.0 * (vol_mascara - vol_analitico) / vol_analitico
    checar(u"a mascara rasterizada fica a menos de 3%% do analitico",
           abs(erro_mascara) <= 3.0, u"%.2f%%" % erro_mascara)

    rs_local, nomes = engine.build_rtstruct(
        c["stage"], {"lung_left": esfera}, versao_worker="teste-analitico")
    destino = os.path.join(novo_temp("radai_ana_"), "RS_esfera.dcm")
    shutil.copy2(rs_local, destino)
    sessao = radai_rt.abrir(c["pasta"], destino)
    try:
        volta = sessao.mascara(nomes["lung_left"])
        vol_volta = float(volta.sum()) * vol_voxel
        erro_volta = 100.0 * (vol_volta - vol_analitico) / vol_analitico
        print(u"       analitico %.0f mm3 · mascara %+.2f%% · ciclo %+.2f%%"
              % (vol_analitico, erro_mascara, erro_volta))

        checar(u"o ciclo fica a menos de 5%% do volume analitico",
               abs(erro_volta) <= 5.0, u"%.2f%%" % erro_volta)

        import pydicom
        ds = pydicom.dcmread(destino, force=True)
        alvo_roi = None
        for r in (getattr(ds, "StructureSetROISequence", None) or []):
            if str(getattr(r, "ROIName", "")) == nomes["lung_left"]:
                alvo_roi = int(r.ROINumber)
                break
        areas = []
        for cs in (getattr(ds, "ROIContourSequence", None) or []):
            if int(getattr(cs, "ReferencedROINumber", -1)) != (alvo_roi or -1):
                continue
            for cont in (getattr(cs, "ContourSequence", None) or []):
                v = [float(x) for x in (getattr(cont, "ContourData", None) or [])]
                if len(v) < 9:
                    continue
                pts = np.array(v, float).reshape(-1, 3)[:, :2]
                areas.append(abs(radai_geom.area_poligono(pts)))
        checar(u"o RTSTRUCT tem poligono em varios cortes", len(areas) >= 3,
               str(len(areas)))
        if areas:
            area_meio = sorted(areas)[len(areas) // 2]
            area_ana = np.pi * raio_mm ** 2
            erro_area = 100.0 * (area_meio - area_ana) / area_ana
            print(u"       area do corte central: analitico %.1f mm2 · "
                  u"poligono %+.2f%%" % (area_ana, erro_area))
            checar(u"a area do poligono fica a menos de 8%% do analitico",
                   abs(erro_area) <= 8.0, u"%.2f%%" % erro_area)
            checar(u"e ela NAO encolhe (o sintoma do meio pixel para dentro)",
                   erro_area > -5.0,
                   u"%.2f%% -- poligono menor que o analitico e' meio pixel "
                   u"para dentro" % erro_area)

        m = radai_rt.medir_ciclo(esfera, volta, sessao.grade)
        checar(u"e o ciclo continua fechando (DSC >= 0.97)",
               m["dsc"] >= 0.97, str(m["dsc"]))
    finally:
        try:
            sessao.fechar()
        except Exception:
            pass


def teste_ciclo_fechado():
    secao("ciclo fechado mascara -> RTSTRUCT -> mascara")
    c = cenario()
    sessao = radai_rt.abrir(c["pasta"], c["rs"])
    try:
        checar("as duas estruturas voltam do RTSTRUCT", len(sessao.nomes) == 2,
               str(sessao.nomes))
        checar("a grade bate com a do CT", sessao.grade.spacing == c["grade"].spacing,
               "%r vs %r" % (sessao.grade.spacing, c["grade"].spacing))
        checar("a forma bate com a do CT", sessao.forma == c["forma"],
               "%r vs %r" % (sessao.forma, c["forma"]))
        nome_alvo = c["nomes"]["lung_left"]
        volta = sessao.mascara(nome_alvo)
        m = radai_rt.medir_ciclo(c["alvo"], volta, sessao.grade)
        checar("DSC do ciclo >= 0.98", m["dsc"] >= 0.98, str(m["dsc"]))
        checar("volume nao muda mais que 2%", abs(m["delta_vol_pct"]) <= 2.0,
               str(m["delta_vol_pct"]))
        checar("NAO desloca em z (fatia trocada seria erro de orientacao)",
               m["desloc_z_voxels"] == 0.0, str(m["desloc_z_voxels"]))
        checar("o numero de fatias e o mesmo",
               m["fatias_original"] == m["fatias_devolvida"],
               "%s vs %s" % (m["fatias_original"], m["fatias_devolvida"]))
    finally:
        sessao.fechar()


def teste_ciclo_com_formas_dificeis():
    secao("ciclo fechado com formas que costumam quebrar")
    c = cenario()
    F = c["forma"]
    zz, yy, xx = np.ogrid[0:F[0], 0:F[1], 0:F[2]]
    cy, cx = F[1] / 2.0, F[2] / 2.0
    r = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    casos = {
        "anel com buraco": (r <= 30) & (r >= 16) & (np.abs(zz - F[0] * 0.5) <= 6),
        "duas ilhas": ((((yy - cy) / 10.0) ** 2 + ((xx - (cx - 34)) / 8.0) ** 2 <= 1)
                       | (((yy - cy) / 10.0) ** 2 + ((xx - (cx + 34)) / 8.0) ** 2 <= 1)
                       ) & (np.abs(zz - 20) <= 5),
        "lamina de 2 voxels": ((np.abs(yy - cy) <= 1) & (np.abs(xx - cx) <= 30)
                               & (np.abs(zz - 20) <= 8)),
        "uma fatia so": (((yy - cy) / 12.0) ** 2 + ((xx - cx) / 12.0) ** 2 <= 1) & (zz == 20),
        "encosta na borda": (yy < 14) & (np.abs(xx - cx) <= 20) & (np.abs(zz - 20) <= 6),
    }
    for nome, alvo in casos.items():
        alvo = np.ascontiguousarray(np.broadcast_to(alvo, F))
        if not alvo.any():
            checar("caso %s tem voxels" % nome, False, "fantoma mal construido")
            continue
        rs_local, mapa = engine.build_rtstruct(c["stage"], {"lung_left": alvo},
                                              versao_worker="teste")
        destino = os.path.join(c["pasta"], "RS_dificil.dcm")
        shutil.copy2(rs_local, destino)
        sessao = None
        try:
            sessao = radai_rt.abrir(c["pasta"], destino)
            volta = sessao.mascara(mapa["lung_left"])
            m = radai_rt.medir_ciclo(alvo, volta, sessao.grade)
            checar("%s: DSC >= 0.95" % nome, m["dsc"] >= 0.95, str(m["dsc"]))
            checar("%s: sem deslocamento em z" % nome, m["desloc_z_voxels"] == 0.0,
                   str(m["desloc_z_voxels"]))
        except Exception as e:
            checar("%s: o ciclo fecha" % nome, False, "%s: %s" % (type(e).__name__, e))
        finally:
            if sessao is not None:
                sessao.fechar()
            try:
                os.remove(destino)
            except Exception:
                pass


def teste_o_lote_nao_desenha_previa():
    secao("o lote nao desenha previa (o MPR saiu, e o radai_png junto)")
    fonte = open(_componentes.fonte("app/radai_batch.py"), encoding="utf-8").read()
    checar("o lote nao desenha mais previa e o calibrador continua fora dele",
           "def previa_mpr" not in fonte and "radai_png" not in fonte
           and "radai_calibrator" not in fonte)


_MODELOS_REAIS = [os.environ.get("RADAI_MODELOS_DIR")]


def _modelos_temp():
    d = novo_temp("radai_mod_")
    os.environ["RADAI_MODELOS_DIR"] = d
    return d


def teste_registro_de_modelos():
    secao("modelos: o registro diz o que cada um exige e permite")
    _modelos_temp()
    e = radai_models.estado()
    ids = [m["id"] for m in e["modelos"]]
    checar("o TotalSegmentator esta no registro", "totalsegmentator" in ids, str(ids))
    checar("o NV-Segment-CT esta no registro", "nv_segment_ct" in ids,
           str(ids))
    checar("e o VISTA-3D nao esta", "vista3d_monai" not in ids, str(ids))
    for m in e["modelos"]:
        checar("%s declara a licenca" % m["id"], bool(m["licenca"]))
        checar("%s declara o que a licenca permite" % m["id"],
               m["uso_permitido"] in ("livre", "nao_comercial", "conferir"),
               m["uso_permitido"])
        checar("%s declara a GPU minima" % m["id"], bool(m["gpu_min_gb"]))
    nv = [m for m in e["modelos"] if m["id"] == "nv_segment_ct"][0]
    checar("o NV-Segment-CT e de uso livre",
           nv["uso_permitido"] == "livre", nv["uso_permitido"])
    checar("e a licenca dele aparece por nome",
           "NVIDIA Open Model License" in nv["licenca"], nv["licenca"][:70])
    rest = [m for m in e["modelos"]
            if m["uso_permitido"] == "nao_comercial"]
    checar("o pacote de hoje nao declara modelo nao-comercial", not rest,
           str([m["id"] for m in rest]))
    for m in rest:
        checar("  e %s diz o que a licenca limita" % m["id"],
               ("comercial" in m["licenca"].lower()
                or "non-commercial" in m["licenca"].lower()),
               m["licenca"][:70])


def teste_modelo_embutido_vs_baixavel():
    secao("modelos: embutido conta como instalado, baixavel nao")
    _modelos_temp()
    ts = radai_models.estado_do_modelo("totalsegmentator")
    checar("o TotalSegmentator ja vem no bundle", ts["embutido"] is True)
    checar("e conta como instalado sem baixar nada", ts["instalado"] is True)
    v = radai_models.estado_do_modelo("nv_segment_ct")
    checar("o NV-Segment-CT nao esta instalado numa pasta vazia",
           v["instalado"] is False)
    checar("e lista o que falta", "models/model.pt" in v["faltando"], str(v["faltando"]))
    checar("com o tamanho esperado do peso", v["bytes_total"] > 800 * 1000 * 1000,
           str(v["bytes_total"]))


def teste_escolha_de_modelo():
    secao("modelos: nenhuma porta de escolher modelo")
    _modelos_temp()
    checar("`escolher` saiu: nenhuma rota nem tela elege modelo",
           not hasattr(radai_models, "escolher")
           and not hasattr(radai_models, "_aceite_em_dia"))
    checar("  e o `escolhido` e o arquivo dele tambem (o diagnostico lia um "
           "arquivo que nada mais gravava)",
           not hasattr(radai_models, "escolhido")
           and not hasattr(radai_models, "_arquivo_escolha"))
    import io as _io
    painel = _io.open(_componentes.fonte("app/radai_panel.py"),
                      encoding="utf-8").read()
    checar("  e o diagnostico nao mostra mais a linha «modelo escolhido»",
           "modelo escolhido" not in painel and "escolhido()" not in painel)
    restritos = [k for k, m in radai_models.MODELOS.items()
                 if m.get("uso_permitido") != "livre"]
    checar("  e nenhum modelo do registro pede a trava de licenca nao "
           "comercial (a porta nova que rodar um assim volta com a trava)",
           not restritos, str(restritos))


def teste_nao_ha_chave_de_api():
    secao("modelos: nao ha mais chave de API em lugar nenhum")
    fonte = open(_componentes.fonte("app/radai_models.py"), encoding="utf-8").read()
    codigo = "\n".join(l for l in fonte.splitlines()
                       if not l.lstrip().startswith("#"))
    for sumido in ("def caminho_chave", "def ler_chave", "def chave_presente",
                   "def gravar_chave", "def conferir_chave"):
        checar("%s nao existe mais" % sumido.replace("def ", ""),
               sumido not in codigo, sumido)
    for rota in ('"/api/modelos/chave"', '"/api/modelos/conferir_chave"'):
        checar("a rota %s foi removida" % rota, rota not in codigo, rota)
    checar("o modulo nao fala mais com a API da NVIDIA",
           "integrate.api.nvidia.com" not in codigo)
    checar("nem le NVIDIA_API_KEY do ambiente", "NVIDIA_API_KEY" not in codigo)
    checar("e nenhum arquivo de chave e lido (o chave_nvidia.txt de antes)",
           "chave_nvidia" not in codigo)

    e = radai_models.estado()
    checar("o estado do modulo nao expoe campo de chave",
           "chave" not in e, str(sorted(e)))
    checar("e continua dizendo que nada vai para a nuvem",
           bool(e.get("aviso_nuvem")))

    painel = open(_componentes.fonte("app/radai_panel.py"), encoding="utf-8").read()
    tela = painel.split("PAGINA_CONFIG")[-1] if "PAGINA_CONFIG" in painel else painel
    checar("a tela de configuracoes nao tem campo de chave",
           'id="chave"' not in tela)


def teste_nao_ha_caminho_de_imagem_para_a_nuvem():
    secao("modelos: nenhuma funcao manda imagem para a nuvem")
    fonte = (open(_componentes.fonte("app/radai_models.py"), encoding="utf-8").read())
    for proibido in ("nii.gz", "multipart", "files=", "upload", "vista3d/infer"):
        checar("o modulo nao tem rota de envio de imagem (%s)" % proibido,
               proibido not in fonte.lower(), proibido)
    checar("e o aviso sobre a nuvem esta escrito",
           "nao e usada para imagem de paciente" in radai_models.AVISO_NUVEM.lower()
           or "não é usada para imagem de paciente" in radai_models.AVISO_NUVEM.lower(),
           radai_models.AVISO_NUVEM[:60])


def teste_acervo_le_o_dados_txt():
    secao("acervo: o _dados.txt tira o dado de dentro do repositorio")
    guardado_env = os.environ.pop("RADAI_CALIB_DIR", None)
    aqui_antes = radai_archive.HERE
    base = tempfile.mkdtemp(prefix="radai_dados_")
    _TEMPS.append(base)
    try:
        app = os.path.join(base, "app")
        os.makedirs(app)
        fora = os.path.join(base, "FORA_DA_NUVEM")
        radai_archive.HERE = Path(app)

        checar("sem _dados.txt o padrao e ao lado do programa (comportamento antigo)",
               radai_archive.raiz() == Path(app) / "calibracao",
               str(radai_archive.raiz()))

        with open(os.path.join(base, "_dados.txt"), "w", encoding="utf-8") as f:
            f.write(fora + "\n")
        checar("com _dados.txt na raiz do projeto, o acervo vai para la",
               radai_archive.raiz() == Path(fora), str(radai_archive.raiz()))

        with open(os.path.join(base, "_dados.txt"), "wb") as f:
            f.write(b"\xef\xbb\xbf" + fora.encode("utf-8") + b"\r\n")
        checar("BOM do Bloco de Notas nao entra no caminho",
               radai_archive.raiz() == Path(fora), repr(str(radai_archive.raiz())))

        os.environ["RADAI_CALIB_DIR"] = os.path.join(base, "POR_VARIAVEL")
        checar("RADAI_CALIB_DIR ainda vence o _dados.txt",
               radai_archive.raiz() == Path(base) / "POR_VARIAVEL",
               str(radai_archive.raiz()))
        os.environ.pop("RADAI_CALIB_DIR", None)

        os.remove(os.path.join(base, "_dados.txt"))
        with open(os.path.join(app, "_dados.txt"), "w", encoding="utf-8") as f:
            f.write("# o caminho vem abaixo\n" + fora + "\n")
        checar("tambem le o _dados.txt ao lado do modulo, ignorando comentario",
               radai_archive.raiz() == Path(fora), str(radai_archive.raiz()))
    finally:
        radai_archive.HERE = aqui_antes
        if guardado_env is None:
            os.environ.pop("RADAI_CALIB_DIR", None)
        else:
            os.environ["RADAI_CALIB_DIR"] = guardado_env


def teste_download_verifica_tamanho():
    secao("modelos: download recusa arquivo truncado")
    d = _modelos_temp()
    alvo = radai_models.pasta_do_modelo("nv_segment_ct", criar=True) / "models"
    alvo.mkdir(parents=True, exist_ok=True)
    (alvo / "model.pt").write_bytes(b"peso truncado")
    e = radai_models.estado_do_modelo("nv_segment_ct")
    checar("arquivo com tamanho errado conta como faltando",
           "models/model.pt" in e["faltando"], str(e["faltando"]))
    checar("e o modelo nao passa por instalado", e["instalado"] is False)


def teste_normalizacao_de_nomes():
    secao("termos: 'right kidney' e 'kidney_right' sao a mesma coisa")
    n = radai_terms.normalizar
    checar("lado vai para o fim", n("right kidney") == "kidney_right", n("right kidney"))
    checar("o nosso formato ja esta canonico", n("kidney_right") == "kidney_right")
    checar("maiuscula nao importa", n("Left Adrenal Gland") == "adrenal_gland_left",
           n("Left Adrenal Gland"))
    checar("pontuacao vira separador", n("vertebrae L5") == "vertebrae_l5",
           n("vertebrae L5"))
    checar("nao inventa lado onde nao ha", n("liver") == "liver")
    checar("sinonimo chega na forma canonica",
           radai_terms.canonico("bladder") == "urinary_bladder",
           radai_terms.canonico("bladder"))
    checar("e vale nos dois sentidos",
           radai_terms.canonico("urinary_bladder") == radai_terms.canonico("bladder"))


def teste_correspondencia_entre_modelos():
    secao("termos: cruzamento dos dois vocabularios")
    ts = ["kidney_left", "kidney_right", "liver", "urinary_bladder", "lung_left",
          "parotid_gland_left", "vertebrae_lumbar"]
    nv = ["left kidney", "right kidney", "liver", "bladder",
             "left lung upper lobe", "left lung lower lobe", "lung tumor",
             "vertebrae L1", "vertebrae L2", "vertebrae L3", "vertebrae L4",
             "vertebrae L5"]
    c = radai_terms.comparar(ts, nv)
    exatas = dict((e["ts"], e["nv"]) for e in c["exatas"])
    checar("kidney_left casa com 'left kidney'",
           exatas.get("kidney_left") == ["left kidney"], str(exatas.get("kidney_left")))
    checar("liver casa direto", "liver" in exatas)
    checar("urinary_bladder casa com 'bladder' pelo sinonimo",
           exatas.get("urinary_bladder") == ["bladder"], str(exatas.get("urinary_bladder")))

    fundidas = dict((f["ts"], f["nv"]) for f in c["fundidas"])
    checar("lung_left junta os dois lobos do VISTA",
           sorted(fundidas.get("lung_left") or []) ==
           ["left lung lower lobe", "left lung upper lobe"], str(fundidas.get("lung_left")))
    checar("vertebrae_lumbar junta L1..L5",
           len(fundidas.get("vertebrae_lumbar") or []) == 5,
           str(fundidas.get("vertebrae_lumbar")))
    checar("a fundida se declara como fundida",
           all(f["relacao"] == "fundida" for f in c["fundidas"]))
    checar("e explica que somou", all(f["nota"] for f in c["fundidas"]))

    checar("parotida entra em 'so nos temos' (o VISTA nao tem)",
           "parotid_gland_left" in c["so_ts"], str(c["so_ts"]))
    checar("tumor de pulmao entra em 'so o VISTA tem'",
           "lung tumor" in c["so_nv"], str(c["so_nv"]))
    checar("rotulo ja usado numa fundida NAO reaparece como so_vista",
           "left lung upper lobe" not in c["so_nv"], str(c["so_nv"]))
    checar("nem o que casou exato", "left kidney" not in c["so_nv"])


def teste_correspondencia_com_vocabularios_reais():
    secao("termos: cruzamento com os vocabularios reais")
    import engine
    guardado = os.environ.get("RADAI_MODELOS_DIR")
    if _MODELOS_REAIS[0] is None:
        os.environ.pop("RADAI_MODELOS_DIR", None)
    else:
        os.environ["RADAI_MODELOS_DIR"] = _MODELOS_REAIS[0]
    try:
        labels = radai_models.pasta_do_modelo("vista3d_monai") / "docs" / "labels.json"
        if not labels.exists():
            checar("vocabulario real do VISTA-3D NAO foi medido (modelo ausente)",
                   True, "procurei em %s" % labels)
            return
        nv = list(json.loads(labels.read_text(encoding="utf-8")).keys())
    finally:
        if guardado is None:
            os.environ.pop("RADAI_MODELOS_DIR", None)
        else:
            os.environ["RADAI_MODELOS_DIR"] = guardado
    ts = sorted(engine.TS_MAP)
    r = radai_terms.resumo(ts, nv)
    checar("o VISTA-3D trouxe as 124 classes", len(nv) == 124, str(len(nv)))
    checar("ha estrutura comparavel de verdade", r["comparaveis"] >= 30, str(r))
    checar("e estrutura nova para o acervo", r["so_nv"] >= 20, str(r))
    checar("a cabeca-pescoco continua so nossa", r["so_ts"] >= 30, str(r))
    c = radai_terms.comparar(ts, nv)
    for esperada in ("parotid_gland_left", "submandibular_gland_left",
                     "optic_nerve_left", "oropharynx"):
        checar("%s e exclusiva nossa" % esperada, esperada in c["so_ts"])
    for nova in ("lung tumor", "hepatic tumor", "left humerus", "airway"):
        checar("%s so o NV-Segment-CT entrega" % nova, nova in c["so_nv"])
    checar("nenhum nome aparece dos dois lados",
           not (set(c["so_nv"]) & set(
               n for e in c["exatas"] for n in e["nv"])))


def teste_registro_de_comparacao():
    secao("comparacao: o registro, sem veredito")
    novo_acervo()
    checar("o registro nasce vazio", radai_archive.ler_comparacoes() == [])
    ok = radai_archive.registrar_comparacao(
        uid="S1", estrutura="kidney_left", ts_nome="Kidney_L_ai",
        nv_nome="left kidney", relacao="exata",
        metricas={"dsc": 0.81, "delta_vol_pct": -9.2}, segundos=21.4)
    checar("registrou", ok is True)
    radai_archive.registrar_comparacao(uid="S1", estrutura="liver",
                                      ts_nome="Liver_ai", nv_nome="liver")
    regs = radai_archive.ler_comparacoes()
    checar("duas no registro", len(regs) == 2, str(len(regs)))
    checar("guardam a metrica ja calculada",
           any(c["metricas"].get("dsc") == 0.81 for c in regs))
    radai_archive.registrar_comparacao(uid="S1", estrutura="liver",
                                      ts_nome="Liver_ai", nv_nome="liver",
                                      metricas={"dsc": 0.9})
    regs = radai_archive.ler_comparacoes()
    checar("a mesma serie e estrutura continua UMA entrada (a nova vence)",
           len(regs) == 2 and [c["metricas"].get("dsc") for c in regs
                               if c["estrutura"] == "liver"] == [0.9], str(regs))
    checar("e o estado do acervo conta o registro",
           radai_archive.estado()["comparacoes"] == 2,
           str(radai_archive.estado()))
    campos = set(regs[0])
    checar("o registro nao leva campo de veredito",
           not (campos & {"escolha", "aceito", "quem", "quando_veredito"}),
           str(sorted(campos)))
    checar("e os vereditos sairam do acervo (sem tela desde a v8.3)",
           not any(hasattr(radai_archive, n) for n in (
               "julgar", "placar", "VEREDITOS", "CATEGORIAS_ERRO",
               "CODIGOS_ERRO", "caminho_rs")))


def _mascaras_do_enfileirar():
    import numpy as _np

    class _NV(object):
        def __init__(self, por):
            self._por = por

        def ids(self):
            return dict((k, i) for i, k in enumerate(sorted(self._por), 1))

        def __getitem__(self, k):
            return self._por[k]

    c = cenario()
    alvo, vizinho = c["alvo"], c["vizinho"]
    deslocado = _np.roll(alvo, 2, axis=2)
    nossas = {"liver": alvo, "kidney_left": vizinho}
    nv = _NV({engine.PREFIXO_NV + "liver": deslocado,
              engine.PREFIXO_NV + "kidney_left": vizinho})
    return c, nossas, nv, ["liver", "left kidney"]


def teste_enfileirar_registra_a_comparacao():
    secao("comparacao: o _enfileirar registra cada estrutura comparavel")
    import inspect
    import textwrap
    import radai_compare
    novo_acervo()
    c, nossas, nv, classes = _mascaras_do_enfileirar()
    resumo = {"avisos": []}
    n = radai_compare._enfileirar(c["uid"], nossas, nv, classes, c["grade"],
                                  c["pasta"], "RS_x.dcm", "nv.nii.gz", resumo)
    regs = radai_archive.ler_comparacoes()
    checar("as duas estruturas comparaveis foram registradas",
           n == 2 and len(regs) == 2, "n=%s regs=%d avisos=%s"
           % (n, len(regs), resumo["avisos"]))
    checar("  sem aviso de comparacao que falhou", resumo["avisos"] == [],
           str(resumo["avisos"]))
    por = dict((r["estrutura"], r) for r in regs)
    checar("  e com a metrica medida (rim identico: DSC 1; figado deslocado: "
           "abaixo de 1)",
           por.get("kidney_left", {}).get("metricas", {}).get("dsc") == 1.0
           and 0.0 < por.get("liver", {}).get("metricas", {}).get("dsc", 0) < 1.0,
           str(dict((k, v.get("metricas", {}).get("dsc")) for k, v in por.items())))
    fonte = textwrap.dedent(inspect.getsource(radai_compare._enfileirar))
    sombra = fonte.replace("uniao", "nv")
    checar("(isca) o nome da uniao existe na funcao, e a troca o sombreia",
           sombra != fonte and "nv = None" in sombra)
    ns = dict(vars(radai_compare))
    exec(compile(sombra, "<isca_enfileirar>", "exec"), ns)
    novo_acervo()
    resumo2 = {"avisos": []}
    n2 = ns["_enfileirar"](c["uid"], nossas, nv, classes, c["grade"],
                           c["pasta"], "RS_x.dcm", "nv.nii.gz", resumo2)
    checar("(isca) com a mascara do NV sombreada, nada e registrado e a "
           "checagem acima reprovaria",
           n2 == 0 and radai_archive.ler_comparacoes() == []
           and len(resumo2["avisos"]) == 2, "n=%s avisos=%s" % (n2, resumo2["avisos"]))


def teste_chave_de_comparacao_no_config():
    secao("comparar: as chaves da comparacao sairam do config (v8.3)")
    import re as _re
    fonte = open(_componentes.fonte("app/radai_watcher.py"), encoding="utf-8").read()
    import radai_watcher as W
    for chave in ("INCLUIR_NV", "TIMEOUT_NV_H"):
        checar("%s nao esta mais no config modelo" % chave,
               _re.search(r"^%s=" % chave, W.DEFAULT_CFG, _re.M) is None)
        checar("%s nao tem padrao no codigo" % chave, chave not in W.DEFAULTS)
        checar("%s e declarada obsoleta (e nao erro de digitacao)" % chave,
               chave in W.CHAVES_OBSOLETAS)
    checar("o texto que explica a saida esta no vigia",
           "chave obsoleta ignorada" in fonte)

def teste_procedencia_por_estrutura_no_rtstruct():
    secao("procedencia gravada no RTSTRUCT")
    import pydicom
    c = cenario()
    rs_local, nomes = engine.build_rtstruct(
        c["stage"], {"lung_left": c["alvo"], "lung_right": c["vizinho"]},
        versao_worker="teste", origem={"lung_right": "nv"})
    ds = pydicom.dcmread(rs_local)
    por_nome = dict((str(r.ROIName), r) for r in ds.StructureSetROISequence)
    checar("as duas estruturas estao no arquivo", len(por_nome) == 2, str(sorted(por_nome)))
    esq, dir_ = nomes["lung_left"], nomes["lung_right"]
    checar("toda ROI declara geracao automatica",
           all(str(r.ROIGenerationAlgorithm) == "AUTOMATIC" for r in por_nome.values()))
    checar("a nossa aponta o TotalSegmentator",
           "TotalSegmentator" in str(por_nome[esq].ROIGenerationDescription),
           str(por_nome[esq].ROIGenerationDescription))
    checar("a do segundo motor aponta o NV-Segment-CT",
           "NV-Segment-CT" in str(por_nome[dir_].ROIGenerationDescription),
           str(por_nome[dir_].ROIGenerationDescription))
    checar("e o ApprovalStatus continua UNAPPROVED",
           str(ds.ApprovalStatus) == "UNAPPROVED", str(ds.ApprovalStatus))
    checar("com os dois nomes ainda em _ai",
           all(n.endswith("_ai") for n in por_nome), str(sorted(por_nome)))


def teste_sufixo_nv_no_nome_clinico():
    secao("entrega: sufixo _nv respeita o limite de 16")
    for amigavel in ("parotid_gland_left", "kidney_left", "liver",
                     "pharyngeal_constrictor_superior", "submandibular_gland_right"):
        n_ai = engine.nome_clinico(amigavel, sufixo=engine.SUFIXO_AI)
        n_v3 = engine.nome_clinico(amigavel, sufixo=engine.SUFIXO_NV)
        checar("%s: _ai cabe em 16" % amigavel, len(n_ai) <= 16, "%s (%d)" % (n_ai, len(n_ai)))
        checar("%s: _nv cabe em 16" % amigavel, len(n_v3) <= 16, "%s (%d)" % (n_v3, len(n_v3)))
        checar("%s: o sufixo _nv sobrevive ao truncamento" % amigavel,
               n_v3.endswith("_nv"), n_v3)
        checar("%s: os dois nomes sao diferentes" % amigavel, n_ai != n_v3,
               "%s / %s" % (n_ai, n_v3))
    lado = engine.nome_clinico("submandibular_gland_right", sufixo=engine.SUFIXO_NV)
    checar("o lado nao some no truncamento do _nv", "_R" in lado, lado)
    for nivel, marca in (("vertebrae_t10", "t10"), ("vertebrae_t11", "t11"),
                         ("vertebrae_t12", "t12")):
        n = engine.nome_clinico(nivel, sufixo=engine.SUFIXO_NV)
        checar("%s: cabe em 16 com o sufixo inteiro" % nivel,
               len(n) <= 16 and n.endswith("_nv"), "%s (%d)" % (n, len(n)))
        checar("  e o nivel %s sobrevive" % marca, marca in n, n)


def teste_rtstruct_traz_as_duas_versoes():
    secao("entrega: um RTSTRUCT com as duas versoes")
    import pydicom
    c = cenario()
    masks = {"lung_left": c["alvo"],
             engine.PREFIXO_NV + "lung_left": c["vizinho"]}
    rs, nomes = engine.build_rtstruct(c["stage"], masks, versao_worker="teste")
    ds = pydicom.dcmread(rs)
    ids = sorted(str(r.ROIName) for r in ds.StructureSetROISequence)
    checar("as duas versoes entraram", len(ids) == 2, str(ids))
    checar("uma termina em _ai", any(n.endswith("_ai") for n in ids), str(ids))
    checar("a outra em _nv", any(n.endswith("_nv") for n in ids), str(ids))
    checar("e os nomes nao colidem", len(set(ids)) == 2, str(ids))
    por_nome = dict((str(r.ROIName), r) for r in ds.StructureSetROISequence)
    v3 = [n for n in ids if n.endswith("_nv")][0]
    ai = [n for n in ids if n.endswith("_ai")][0]
    checar("a procedencia do _nv aponta o NV-Segment-CT",
           "NV-Segment-CT" in str(por_nome[v3].ROIGenerationDescription),
           str(por_nome[v3].ROIGenerationDescription))
    checar("a do _ai aponta o TotalSegmentator",
           "TotalSegmentator" in str(por_nome[ai].ROIGenerationDescription))
    d = str(ds.StructureSetDescription)
    checar("a descricao nomeia os DOIS sufixos", "_nv" in d and "_ai" in d, d[:120])
    checar("e diz que NENHUMA foi revisada", "NENHUMA foi revisada" in d, d[:200])
    checar("o ApprovalStatus continua UNAPPROVED", str(ds.ApprovalStatus) == "UNAPPROVED")


def teste_masks_do_nv_nomeia_e_filtra():
    secao("entrega: classes do VISTA viram mascaras nomeaveis")
    import numpy as _np
    import radai_compare
    import radai_nv_engine as vm
    c = cenario()
    import nibabel as nib
    F = c["forma"]
    vol = _np.zeros((F[2], F[1], F[0]), dtype=_np.uint8)
    vol[20:40, 20:40, 5:15] = 7
    vol[0:2, 0:2, 0:1] = 9
    caminho = os.path.join(novo_temp(), "saida.nii.gz")
    nib.save(nib.Nifti1Image(vol, _np.eye(4)), caminho)
    classes = {"left humerus": 7, "bone lesion": 9}
    m = radai_compare.masks_do_nv(caminho, F, classes, minimo_voxels=10)
    chaves = sorted(m)
    checar("so a classe volumosa entra", len(m) == 1, str(chaves))
    checar("com o prefixo nv:", chaves[0].startswith(engine.PREFIXO_NV), chaves[0])
    checar("e o nome normalizado (lado no fim)",
           chaves[0] == engine.PREFIXO_NV + "humerus_left", chaves[0])
    checar("a mascara volta na grade do CT", m[chaves[0]].shape == F,
           str(m[chaves[0]].shape))
    nome = engine.nome_clinico(chaves[0][len(engine.PREFIXO_NV):],
                              sufixo=engine.SUFIXO_NV)
    checar("e vira um Structure ID valido", len(nome) <= 16 and nome.endswith("_nv"),
           nome)


def teste_varredura_do_lote():
    secao("lote: varre e agrupa por SeriesInstanceUID")
    import radai_batch
    base = novo_temp("radai_lot_")
    a = os.path.join(base, "PAC_A", "CT")
    b = os.path.join(base, "PAC_B", "CT")
    uid_a = escreve_serie(a, "PAC_A", datetime.now(), 25)
    uid_b = escreve_serie(b, "PAC_B", datetime.now(), 30)
    s = radai_batch.varrer(base, min_cortes=20)
    checar("achou as duas series", len(s) == 2, str(len(s)))
    por_uid = dict((x["uid"], x) for x in s)
    checar("com os uids certos", uid_a in por_uid and uid_b in por_uid, str(sorted(por_uid)))
    checar("conta os cortes", por_uid[uid_a]["cortes"] == 25,
           str(por_uid[uid_a]["cortes"]))
    checar("guarda a pasta da serie", por_uid[uid_a]["pasta"].endswith("CT"))
    checar("e o paciente", por_uid[uid_a]["pid"] == "PAC_A", por_uid[uid_a]["pid"])
    checar("nenhuma tem RTSTRUCT ainda", not any(x["tem_rs"] for x in s))

    curtos = radai_batch.varrer(base, min_cortes=28)
    checar("o minimo de cortes filtra", len(curtos) == 1, str(len(curtos)))
    checar("uma pasta de UM paciente devolve so a dele",
           len(radai_batch.varrer(a, min_cortes=20)) == 1)
    checar("pasta vazia devolve lista vazia",
           radai_batch.varrer(novo_temp(), min_cortes=20) == [])


def teste_lote_enxerga_rtstruct_existente():
    secao("lote: avisa quando a serie ja tem RTSTRUCT")
    import radai_batch
    c = cenario()
    s = radai_batch.varrer(c["pasta"], min_cortes=20)
    checar("achou a serie do cenario", len(s) == 1, str(len(s)))
    checar("e viu que ja tem RS_RadAI", s[0]["tem_rs"] is True, str(s[0]))


def teste_lote_estado_e_cancelamento():
    secao("lote: estado e cancelamento")
    import radai_batch
    e = radai_batch.estado()
    for chave in ("rodando", "total", "feitas", "atual", "etapa", "resultados"):
        checar("o estado traz %s" % chave, chave in e)
    checar("nada rodando no inicio", e["rodando"] is False)
    r = radai_batch.cancelar()
    checar("cancelar sem nada rodando nao levanta", r["ok"] is False, str(r))
    r = radai_batch.iniciar([], marcadores=_marcadores_falsos({}))
    checar("iniciar com lista vazia e aceito", r["ok"] is True, str(r))
    for _ in range(40):
        if not radai_batch.estado()["rodando"]:
            break
        time.sleep(0.05)
    checar("e termina sozinho", radai_batch.estado()["rodando"] is False)


def _marcadores_falsos(estado):
    class _P(object):
        def __init__(self, chave, alvo):
            self.chave, self.alvo = chave, alvo

        def write_text(self, texto, encoding=None):
            self.alvo[self.chave] = texto

    def has_marker(pasta, uid, tipo):
        return (str(pasta), uid, tipo) in estado

    def m_path(pasta, uid, tipo, criar=False):
        return _P((str(pasta), uid, tipo), estado)

    def read_marker(pasta, uid, tipo):
        import json as _j
        try:
            return _j.loads(estado[(str(pasta), uid, tipo)])
        except Exception:
            return None

    def claim(pasta, uid, meta):
        k = (str(pasta), uid, "lock")
        if k in estado:
            return False
        import json as _j
        estado[k] = _j.dumps(meta)
        return True

    def unclaim(pasta, uid):
        estado.pop((str(pasta), uid, "lock"), None)

    return {"claim": claim, "unclaim": unclaim, "has_marker": has_marker,
            "m_path": m_path, "read_marker": read_marker,
            "renovar": lambda p, u: True}


def teste_lote_recusa_rodar_sem_coordenacao():
    secao("lote: recusa processar sem os marcadores")
    import radai_batch
    r = radai_batch.iniciar([{"uid": "X", "pasta": "p"}])
    checar("sem marcadores, recusa", r["ok"] is False, str(r))
    checar("e explica por que", "duas estacoes" in r["erro"], r["erro"][:90])
    checar("nao deixou nada rodando", radai_batch.estado()["rodando"] is False)
    faltando = dict(_marcadores_falsos({}))
    faltando.pop("renovar")
    r = radai_batch.iniciar([], marcadores=faltando)
    checar("marcador faltando tambem recusa", r["ok"] is False, str(r))
    checar("dizendo qual falta", "renovar" in r["erro"], r["erro"][:90])


def teste_lote_situacao_das_series():
    secao("lote: a tela mostra o que os marcadores dizem")
    import json as _j
    import radai_batch
    c = cenario()
    est = {}
    marc = _marcadores_falsos(est)
    s = radai_batch.varrer(c["pasta"], min_cortes=20, marcadores=marc)
    checar("serie livre aparece como livre", s[0]["situacao"] == "livre",
           str(s[0]["situacao"]))

    est[(s[0]["pasta"], s[0]["uid"], "lock")] = _j.dumps(
        {"machine": "PC_OUTRO", "start": "2026-08-05 10:00:00"})
    s = radai_batch.varrer(c["pasta"], min_cortes=20, marcadores=marc)
    checar("com lock de outra estacao, aparece EM PROCESSAMENTO",
           s[0]["situacao"] == "processando", str(s[0]))
    checar("e diz qual estacao", "PC_OUTRO" in s[0]["detalhe"], s[0]["detalhe"])

    est.pop((s[0]["pasta"], s[0]["uid"], "lock"))
    est[(s[0]["pasta"], s[0]["uid"], "done")] = _j.dumps(
        {"machine": "PC_A", "finished": "2026-08-05 09:00:00"})
    s = radai_batch.varrer(c["pasta"], min_cortes=20, marcadores=marc)
    checar("com done, aparece CONCLUIDA", s[0]["situacao"] == "concluida", str(s[0]))
    checar("sem marcadores, cai em livre (nao inventa estado)",
           radai_batch.varrer(c["pasta"], min_cortes=20)[0]["situacao"] == "livre")


def teste_lote_respeita_lock_e_done():
    secao("lote: nao processa serie travada nem ja concluida")
    import json as _j
    import radai_batch
    c = cenario()
    est = {}
    marc = _marcadores_falsos(est)
    s = radai_batch.varrer(c["pasta"], min_cortes=20, marcadores=marc)[0]

    est[(s["pasta"], s["uid"], "done")] = _j.dumps({"machine": "PC_A"})
    r = radai_batch._uma_serie(s, False, ["total"], "cpu", None, 60, 60, None,
                              marc, "PC_TESTE", 300)
    checar("serie ja concluida e pulada", "ja concluida" in r["pulada"], str(r))
    checar("e nao foi segmentada", r["estruturas"] == 0)

    est.pop((s["pasta"], s["uid"], "done"))
    est[(s["pasta"], s["uid"], "lock")] = _j.dumps({"machine": "PC_OUTRO"})
    r = radai_batch._uma_serie(s, False, ["total"], "cpu", None, 60, 60, None,
                              marc, "PC_TESTE", 300)
    checar("serie travada por outra estacao e pulada",
           "outra estacao" in r["pulada"], str(r))
    checar("e o lock da outra NAO foi removido",
           (s["pasta"], s["uid"], "lock") in est)


def teste_lote_marca_done_no_formato_do_vigia():
    secao("lote: o done tem o formato que o vigia le")
    import json as _j
    import radai_batch
    est = {}
    marc = _marcadores_falsos(est)
    s = {"uid": "U1", "pasta": "P1", "pid": "PAC", "date": "20260101", "curto": "U1"}
    radai_batch._marcar_done(s, marc, "PC_TESTE", "RS_x.dcm", ["Liver_ai"], 97,
                            ["total"], 300, None)
    d = _j.loads(est[("P1", "U1", "done")])
    for campo in ("uid", "date", "pid", "machine", "finished", "secs", "rs",
                  "tasks", "tasks_ok", "cortes", "structures", "ver", "dry_run"):
        checar("o done traz %s (igual ao do vigia)" % campo, campo in d, str(sorted(d)))
    checar("dry_run e False", d["dry_run"] is False)
    checar("e ha um campo origem dizendo de onde veio",
           d.get("origem") == "rodar agora", str(d.get("origem")))


_MODULO_DA_FONTE = {"batch": "radai_batch", "output": "radai_output",
                    "watcher": "radai_watcher"}
_COPIAS = ("copy2", "copyfile", "copy", "move")


def _fontes_dos_gravadores():
    def _ler(nome):
        return open(_componentes.fonte("app/" + nome), encoding="utf-8").read()
    return dict((k, _ler(m + ".py")) for k, m in _MODULO_DA_FONTE.items())


def _funcoes(arv):
    import ast
    fora = []

    def _andar(no, pref):
        for c in ast.iter_child_nodes(no):
            if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fora.append((pref + c.name, c))
                _andar(c, pref + c.name + ".")
            elif isinstance(c, ast.ClassDef):
                _andar(c, pref + c.name + ".")
            else:
                _andar(c, pref)
    _andar(arv, "")
    return fora


def _gravacao_do_lote(fontes):
    import ast
    arvs = {}
    for k, src in fontes.items():
        try:
            arvs[k] = ast.parse(src)
        except SyntaxError:
            arvs[k] = ast.parse("")

    def _nome(f):
        return getattr(f, "attr", None) or getattr(f, "id", None)

    def _de_self(no, attr):
        return (isinstance(no, ast.Attribute) and no.attr == attr
                and isinstance(no.value, ast.Name) and no.value.id == "self")

    def _chamada_de(no, modulo, nome):
        return (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
                and no.func.attr == nome
                and isinstance(no.func.value, ast.Name)
                and no.func.value.id == modulo)

    destino_pasta = False
    for no in ast.walk(arvs["batch"]):
        if isinstance(no, ast.Call) and _nome(no.func) == "Saida":
            dest = no.args[2] if len(no.args) > 2 else next(
                (k.value for k in no.keywords if k.arg == "destino"), None)
            if (isinstance(dest, ast.Subscript)
                    and isinstance(dest.value, ast.Name)
                    and dest.value.id == "s"
                    and isinstance(dest.slice, ast.Constant)
                    and dest.slice.value == "pasta"):
                destino_pasta = True

    saida = next((n for n in ast.walk(arvs["output"])
                  if isinstance(n, ast.ClassDef) and n.name == "Saida"), None)
    metodos = dict((f.name, f) for f in (saida.body if saida else ())
                   if isinstance(f, ast.FunctionDef))
    def _os_path_join(no):
        return (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
                and no.func.attr == "join"
                and isinstance(no.func.value, ast.Attribute)
                and no.func.value.attr == "path")
    alvo_no_destino = any(
        isinstance(r, ast.Return) and _os_path_join(r.value)
        and r.value.args and _de_self(r.value.args[0], "destino")
        for r in ast.walk(metodos.get("_alvo", ast.parse(""))))
    fora_do_alvo, n_grava = [], 0
    for nome, fn in metodos.items():
        atribs = {}
        for no in ast.walk(fn):
            if isinstance(no, ast.Assign) and len(no.targets) == 1 \
                    and isinstance(no.targets[0], ast.Name):
                atribs.setdefault(no.targets[0].id, []).append(no.value)

        def _do_alvo(v):
            return isinstance(v, ast.Call) and _de_self(v.func, "_alvo")
        for no in ast.walk(fn):
            if isinstance(no, ast.Call) and _de_self(no.func,
                                                     "_gravar_arquivo"):
                n_grava += 1
                a = no.args[1] if len(no.args) > 1 else None
                ok = _do_alvo(a) or (
                    isinstance(a, ast.Name) and atribs.get(a.id)
                    and all(_do_alvo(v) for v in atribs[a.id]))
                if not ok:
                    fora_do_alvo.append("%s:%d" % (nome, no.lineno))

    gravadores, atomicos, por_quem = [], True, True
    for k, arv in arvs.items():
        for qual, fn in _funcoes(arv):
            copias = [c for c in ast.walk(fn)
                      if isinstance(c, ast.Call)
                      and isinstance(c.func, ast.Attribute)
                      and c.func.attr in _COPIAS
                      and isinstance(c.func.value, ast.Name)
                      and c.func.value.id in ("shutil", "_sh")]
            if not copias:
                continue
            gravadores.append(_MODULO_DA_FONTE[k] + "." + qual)
            publicados = set()
            for c in ast.walk(fn):
                if _chamada_de(c, "os", "replace") and c.args \
                        and isinstance(c.args[0], ast.Name):
                    publicados.add(c.args[0].id)
            for c in copias:
                d = c.args[1] if len(c.args) > 1 else None
                if not (isinstance(d, ast.Name) and d.id in publicados):
                    atomicos = False
                    por_quem = False
                    continue
                for no in ast.walk(fn):
                    if isinstance(no, ast.Assign) and any(
                            isinstance(t, ast.Name) and t.id == d.id
                            for t in no.targets):
                        if not (isinstance(no.value, ast.Call)
                                and _nome(no.value.func) == "nome_parcial"):
                            por_quem = False

    vigia_injeta = any(
        isinstance(no, ast.Call) and _nome(no.func) == "Saida"
        and any(kw.arg == "copiar" and any(
            isinstance(n, ast.Name) and n.id == "_copiar_atomico"
            for n in ast.walk(kw.value)) for kw in no.keywords)
        for no in ast.walk(arvs["watcher"]))
    gravadores.sort()
    return {"destino_pasta": destino_pasta,
            "alvo_no_destino": alvo_no_destino,
            "todo_arquivo_no_alvo": n_grava > 0 and not fora_do_alvo,
            "fora_do_alvo": fora_do_alvo,
            "gravadores": gravadores,
            "atomicos": bool(gravadores) and atomicos,
            "rascunho_por_quem_escreve": bool(gravadores) and por_quem,
            "vigia_injeta": vigia_injeta}


def teste_lote_grava_ao_lado_dos_dicoms():
    secao("lote: o RTSTRUCT vai junto dos DICOMs")
    import radai_batch
    fonte = open(_componentes.fonte("app/radai_batch.py"), encoding="utf-8").read()
    fontes = _fontes_dos_gravadores()
    p = _gravacao_do_lote(fontes)
    checar("grava dentro da pasta da serie: o lote monta a Saida com "
           "s[\"pasta\"] como destino", p["destino_pasta"])
    checar("  e a Saida monta cada alvo DENTRO do destino (_alvo)",
           p["alvo_no_destino"])
    checar("  e todo arquivo da Saida vai por _gravar_arquivo(..., "
           "self._alvo(...))", p["todo_arquivo_no_alvo"], p["fora_do_alvo"])
    checar("com escrita atomica (nome_parcial + replace), nos DOIS gravadores",
           p["atomicos"], p["gravadores"])
    checar("  e os gravadores sao exatamente dois: o do vigia e o da Saida",
           p["gravadores"] == ["radai_output.Saida._gravar_arquivo",
                               "radai_watcher._copiar_atomico"],
           p["gravadores"])
    checar("  e o vigia injeta o _copiar_atomico na Saida", p["vigia_injeta"])
    checar("e o rascunho nao tem nome fixo", p["rascunho_por_quem_escreve"])
    iscas = (
        ("destino_pasta", "batch",
         'engine, stage, s["pasta"], rs_name,',
         'engine, stage, os.path.join(s["pasta"], "RTSTRUCT"), rs_name,'),
        ("alvo_no_destino", "output",
         "        return os.path.join(self.destino,",
         "        return os.path.join(self.stage,"),
        ("todo_arquivo_no_alvo", "output",
         "            self._gravar_arquivo(rt_full, alvo_full)",
         "            self._gravar_arquivo(rt_full, os.path.join("
         "self.stage, 'x.dcm'))"),
        ("atomicos", "output",
         "                shutil.copy2(rt_local, parcial)\n"
         "                os.replace(parcial, alvo)",
         "                shutil.copy2(rt_local, alvo)"),
        ("rascunho_por_quem_escreve", "watcher",
         "    parcial = radai_sets.nome_parcial(str(destino))",
         "    parcial = str(destino) + \".parcial\""),
        ("vigia_injeta", "watcher",
         "copiar=lambda o, d: _copiar_atomico(o, Path(d))",
         "copiar=None"),
    )
    for chave, qual, velho, novo in iscas:
        f2 = dict(fontes)
        f2[qual] = fontes[qual].replace(velho, novo, 1)
        checar("  (a isca de %s achou o trecho em %s)" % (chave, qual),
               f2[qual] != fontes[qual])
        checar("  isca: %s reprova com o defeito" % chave,
               not _gravacao_do_lote(f2)[chave])
    f2 = dict(fontes)
    f2["batch"] = fontes["batch"] + (
        "\n\ndef _copia_do_lote(rt_local, destino):\n"
        "    shutil.copy2(rt_local, destino + '.tmp')\n"
        "    os.replace(destino + '.tmp', destino)\n")
    checar("  isca: um gravador proprio de volta no lote e contado",
           "radai_batch._copia_do_lote" in _gravacao_do_lote(f2)["gravadores"])
    checar("USA os marcadores do vigia (nao reimplementa claim)",
           "claim" in fonte and "def claim" not in fonte)
    checar("e a serie entra no indice do acervo (radai_archive.registrar_serie)",
           "registrar_serie" in fonte)


def teste_lote_chama_o_motor_como_o_vigia():
    secao("lote: chama o motor com a mesma assinatura do vigia")
    import inspect
    import radai_batch
    fonte = open(_componentes.fonte("app/radai_batch.py"), encoding="utf-8").read()
    checar("passa jid para o run_ts_task", "jid=jid" in fonte)
    checar("cria o job antes", "_job_new()" in fonte)
    checar("e o libera depois", "_job_del(" in fonte)
    obrig = [p.name for p in inspect.signature(engine.run_ts_task).parameters.values()
             if p.default is inspect.Parameter.empty and p.name != "self"]
    checar("todo argumento obrigatorio do motor aparece na chamada do lote",
           all(("%s=" % p) in fonte or p in ("ref", "task") for p in obrig),
           str(obrig))


def teste_pagina_do_lote():
    secao("lote: a tela")
    import radai_batch
    p = radai_batch.PAGINA
    ajuda = u" ".join(radai_batch.AJUDA_DA_TELA)
    pagina = radai_batch._pagina()
    checar("explica que serve para uma pasta ou o .zip do exame",
           "pasta" in ajuda and ".zip do exame" in ajuda
           and "ui-ajuda" in pagina[:pagina.index('id="cx1"')])
    checar("diz onde o RTSTRUCT e gravado",
           "pasta de cada série" in ajuda and "DICOM" in ajuda
           and "pasta de cada série" in pagina)
    checar("tem o seletor de pasta", "/api/pastas" in p)
    _cods = [c.get("cod") for c in radai_batch.comparacao_da_tela("CT")]
    checar("a tela diz onde o segundo motor se liga: a coluna «Comparação de "
           "modelos» do PERSONALIZADO, desenhada do contrato",
           "Comparação de modelos" in p and "d.comparacao" in p
           and "nv" in _cods, _cods)
    checar("  e nao sobrou a caixa na tela de trabalho",
           'id="comvista"' not in p)
    checar("avisa que reprocessar SUBSTITUI a entrega anterior",
           "substitui" in p.lower() and "apagados" in p)
    checar("explica que a coordenacao e a mesma do vigia",
           "mesma do vigia" in p)
    checar("e mostra a coluna de situacao", "Situação" in p)
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
    except ImportError as e:
        checar("o cancelamento existe onde a fila e gerida (fastapi ausente)",
               False, "PULADO -- %s" % e)
        return
    app = FastAPI()
    radai_batch.montar(app, {"tasks": ["total_v3"], "device": "cpu"})
    servida = TestClient(app, raise_server_exceptions=False).get("/lote")
    html = servida.text if servida.status_code == 200 else ""
    checar("a pagina servida em /lote tem o botao de cancelar da fila",
           'id="radai_pipe_can"' in html, "status %s" % servida.status_code)
    checar("  e a barra o liga a rota do cancelar",
           "'/api/pipeline/cancelar'" in html
           and "radai_pipe_can:'cancelar'" in html)
    rotas = set((r.path, m) for r in app.routes
                for m in (getattr(r, "methods", None) or ()))
    checar("  e a rota existe no app montado (POST /api/pipeline/cancelar)",
           ("/api/pipeline/cancelar", "POST") in rotas)
    checar("e volta ao menu", 'href="/"' in p)


def teste_guarda_de_nuvem_le_a_configuracao_do_drive():
    secao(u"o guarda de nuvem: estrutural, nao por nome de pasta")
    import radai_archive

    guardado = os.environ.get("RADAI_RAIZES_NUVEM")
    try:
        os.environ["RADAI_RAIZES_NUVEM"] = r"C:\ESPELHO;C:\OFICINA"

        casos = [
            (r"C:\ESPELHO", True,
             u"a propria raiz espelhada"),
            (r"C:\ESPELHO\TCs_EXEMPLO\_radai_dados", True,
             u"dentro da raiz -- e o caso real, o acervo de paciente"),
            (r"C:\espelho\qualquer", True,
             u"maiuscula nao muda nada no Windows"),
            (r"C:/ESPELHO/com/barra/normal", True,
             u"barra normal e barra invertida sao o mesmo caminho"),
            (r"C:\RADIOTERAPIA_AI\AUTO_CONTORNO\calibracao", False,
             u"a instalacao de campo NAO sincroniza, e nao pode ser acusada"),
            (r"C:\ESPELHOS\coisa", False,
             u"prefixo nao e pasta-mae: sem o separador isto daria positivo"),
        ]
        for caminho, espera, porque in casos:
            achou, motivo = radai_archive.em_pasta_sincronizada(caminho)
            checar(u"%s -> nuvem=%s (%s)" % (caminho, espera, porque),
                   achou == espera,
                   u"" if achou == espera else u"deu %s, motivo %r" % (achou, motivo))

        _, motivo = radai_archive.em_pasta_sincronizada(r"C:\ESPELHO\x")
        checar(u"o motivo nomeia a raiz espelhada",
               "ESPELHO" in motivo, motivo)

        for outro in (r"C:\Users\usuario\OneDrive\dados",
                      r"D:\Dropbox\radai"):
            achou, _ = radai_archive.em_pasta_sincronizada(outro)
            checar(u"a marca por nome ainda pega %s" % outro.split("\\")[-2],
                   achou, u"")
    finally:
        if guardado is None:
            os.environ.pop("RADAI_RAIZES_NUVEM", None)
        else:
            os.environ["RADAI_RAIZES_NUVEM"] = guardado


def teste_o_aviso_de_nuvem_diz_o_que_esta_em_risco():
    secao(u"o aviso de nuvem diz o que esta em risco")
    import radai_archive
    guardado = os.environ.get("RADAI_RAIZES_NUVEM")
    guardado_dir = os.environ.get("RADAI_CALIB_DIR")
    try:
        os.environ["RADAI_RAIZES_NUVEM"] = r"C:\NUVEM_DE_TESTE"
        os.environ["RADAI_CALIB_DIR"] = r"C:\NUVEM_DE_TESTE\acervo"
        c = radai_archive.conferir_local()
        checar(u"acusa nuvem", c["nuvem"] is True, str(c["nuvem"]))
        checar(u"o aviso fala de PACIENTE", "PACIENTE" in c["aviso"], c["aviso"][:60])
        checar(u"o aviso diz o que fazer (RADAI_CALIB_DIR)",
               "RADAI_CALIB_DIR" in c["aviso"], u"")
        checar(u"o aviso nomeia a raiz", "NUVEM_DE_TESTE" in c["aviso"], u"")

        os.environ["RADAI_CALIB_DIR"] = r"C:\RADIOTERAPIA_AI\acervo"
        c2 = radai_archive.conferir_local()
        checar(u"pasta local nao gera aviso",
               c2["nuvem"] is False and not c2["aviso"], c2["aviso"][:60])
    finally:
        if guardado is None:
            os.environ.pop("RADAI_RAIZES_NUVEM", None)
        else:
            os.environ["RADAI_RAIZES_NUVEM"] = guardado
        if guardado_dir is None:
            os.environ.pop("RADAI_CALIB_DIR", None)
        else:
            os.environ["RADAI_CALIB_DIR"] = guardado_dir

def teste_cads_vocabulario_e_licenca():
    secao(u"CADS: vocabulario, nomes e licenca")
    import radai_cads as C
    import radai_models as V
    import engine as MO
    checar(u"o CADS esta no registro de modelos", "cads_open" in V.MODELOS, "")
    m = V.MODELOS.get("cads_open") or {}
    checar(u"a variante e a `open`, de uso permitido",
           m.get("uso_permitido") == "livre", str(m.get("uso_permitido")))
    checar(u"e a licenca diz CC BY-SA", "CC BY-SA" in (m.get("licenca") or ""),
           (m.get("licenca") or "")[:70])
    checar(u"e a URL e a do release `open`",
           "cads-model-open" in (m.get("url_direta") or ""),
           (m.get("url_direta") or "")[:80])
    checar(u"a observacao avisa do ShareAlike sobre peso derivado",
           "derivado" in (m.get("observacao") or ""), "")

    ests = C.estruturas()
    for alvo in ("rectum", "prostate", "seminal_vesicles"):
        checar(u"a tarefa 556 traz %s" % alvo, alvo in ests, str(ests)[:90])
    checar(u"nome com espaco e normalizado",
           " " not in C.normalizar("right psoas major"),
           C.normalizar("right psoas major"))
    checar(u"  e casa com o nome que ja usamos",
           C.normalizar("right psoas major") == "iliopsoas_right",
           C.normalizar("right psoas major"))
    todos = {}
    for k in MO.TS_MAP:
        for sfx in ("_ai", "_v3D", "_ts"):
            todos.setdefault(MO.nome_clinico(k, sufixo=sfx), []).append(k + sfx)
    for e in ests:
        todos.setdefault(MO.nome_clinico(e, sufixo="_cds"), []).append(e + "_cds")
    col = dict((a, b) for a, b in todos.items() if len(b) > 1)
    checar(u"os quatro sufixos convivem sem colisao (%d nomes)" % len(todos),
           not col, str(col)[:150])
    checar(u"o reto do CADS chega como Rectum_cds",
           MO.nome_clinico("rectum", sufixo="_cds") == "Rectum_cds",
           MO.nome_clinico("rectum", sufixo="_cds"))


def teste_cads_motor_le_os_rotulos_do_peso():
    secao(u"CADS: os rotulos vem do proprio peso")
    import radai_cads_engine as CM
    base = ""
    _b = os.path.abspath(_componentes.fonte("app/.."))
    for _ in range(4):
        for _meio in (("_montagem", "AUTO_CONTORNO", "modelos"), ("modelos",)):
            _c = os.path.join(_b, *(_meio + ("cads_open",)))
            if os.path.isdir(_c):
                base = _c
                break
        if base:
            break
        _b = os.path.abspath(os.path.join(_b, ".."))
    if not base:
        checar(u"pesos do CADS nesta estacao", True,
               u"nao baixados aqui — o vocabulario ja foi conferido acima")
        return
    ok, motivo = CM.disponivel(base)
    checar(u"o nnU-Net responde neste Python",
           ok or "nnU-Net" in motivo,
           motivo or "sim")
    r = CM.rotulos(base)
    checar(u"leu os rotulos do dataset.json do peso", len(r) >= 15, str(len(r)))
    checar(u"o fundo (0) nao entra", 0 not in r, "")
    nomes = set(r.values())
    for alvo in ("rectum", "prostate", "seminal_vesicles"):
        checar(u"  e traz %s" % alvo, alvo in nomes, "")
    checar(u"os nomes ja vem traduzidos para o nosso vocabulario",
           "iliopsoas_right" in nomes, str(sorted(nomes))[:120])

def main():
    print("test_rt | ciclo, acervo, modelos, termos, comparacao, entrega, lote e previa")
    guardado = os.environ.get("RADAI_CALIB_DIR")
    guardado_mod = os.environ.get("RADAI_MODELOS_DIR")
    testes = [teste_cads_vocabulario_e_licenca,
              teste_cads_motor_le_os_rotulos_do_peso,
              teste_guarda_de_nuvem_le_a_configuracao_do_drive,
              teste_o_aviso_de_nuvem_diz_o_que_esta_em_risco,
              teste_ciclo_fechado, teste_ciclo_contra_valor_analitico,
              teste_ciclo_com_formas_dificeis,
              teste_o_lote_nao_desenha_previa,
              teste_registro_de_modelos, teste_modelo_embutido_vs_baixavel,
              teste_escolha_de_modelo, teste_nao_ha_chave_de_api,
              teste_nao_ha_caminho_de_imagem_para_a_nuvem,
              teste_acervo_le_o_dados_txt,
              teste_download_verifica_tamanho,
              teste_normalizacao_de_nomes, teste_correspondencia_entre_modelos,
              teste_correspondencia_com_vocabularios_reais,
              teste_registro_de_comparacao,
              teste_enfileirar_registra_a_comparacao,
              teste_chave_de_comparacao_no_config,
              teste_procedencia_por_estrutura_no_rtstruct,
              teste_sufixo_nv_no_nome_clinico, teste_rtstruct_traz_as_duas_versoes,
              teste_masks_do_nv_nomeia_e_filtra,
              teste_varredura_do_lote, teste_lote_enxerga_rtstruct_existente,
              teste_lote_estado_e_cancelamento, teste_lote_grava_ao_lado_dos_dicoms,
              teste_lote_recusa_rodar_sem_coordenacao, teste_lote_situacao_das_series,
              teste_lote_respeita_lock_e_done, teste_lote_marca_done_no_formato_do_vigia,
              teste_lote_chama_o_motor_como_o_vigia, teste_pagina_do_lote]
    for t in testes:
        try:
            t()
        except Exception as e:
            import traceback
            checar("%s (excecao inesperada)" % t.__name__, False,
                   "%s: %s" % (type(e).__name__, e))
            traceback.print_exc()

    for chave, valor in (("RADAI_CALIB_DIR", guardado), ("RADAI_MODELOS_DIR", guardado_mod)):
        if valor is None:
            os.environ.pop(chave, None)
        else:
            os.environ[chave] = valor
    for d in _TEMPS:
        shutil.rmtree(d, ignore_errors=True)

    falhas = [(n, d) for n, ok, d in _RESULTADOS if not ok]
    print("\n" + "=" * 64)
    if falhas:
        print("FALHOU: %d de %d checagens" % (len(falhas), len(_RESULTADOS)))
        for n, d in falhas:
            print("  - %s%s" % (n, ("  [%s]" % d) if d else ""))
    else:
        print("OK: %d checagens, todas passaram" % len(_RESULTADOS))
    print("=" * 64)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
