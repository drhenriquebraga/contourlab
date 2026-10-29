# -*- coding: utf-8 -*-
import os
import sys
import unittest
import hashlib
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from contextlib import contextmanager

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _cleanup
import _componentes

_cleanup.adotar_prefixo("radai_motor89_")
os.environ["RADAI_CALIB_DIR"] = _cleanup.temporaria("radai_motor89_calib_")
os.environ["RADAI_REGISTRO_DIR"] = _cleanup.temporaria("radai_motor89_reg_")

import numpy as np
import pydicom
import engine as E
import radai_geom as G
import radai_output as RO
import radai_rt as RT
import make_test_series as MS


def caixa(forma, z, y, x):
    m = np.zeros(forma, bool)
    m[slice(*z), slice(*y), slice(*x)] = True
    return m


def cruas_cardiacas(forma, variante):
    modelo = caixa(forma, (2, 12), (9, 24), (9, 27))
    cart = caixa(forma, (2, 12), (8, 14 + variante), (8, 11))
    costela = caixa(forma, (1, 13), (8, 15), (5, 9))
    if variante >= 10:
        cart = caixa(forma, (1, 13), (8, 21), (8, 18))
        cart[3:5, 17:21, 14:18] = False
        costela = caixa(forma, (1, 13), (7, 19), (3, 13))
    esterno = caixa(forma, (1, 13), (6, 9), (8, 25))
    vertebra = caixa(forma, (1, 13), (23, 27), (12, 20))
    return {"total_v3": {"heart": modelo, "costal_cartilages": cart,
                         "rib_left_1": costela, "sternum": esterno,
                         "vertebrae_T6": vertebra},
            "trunk_cavities": {"pericardium": caixa(forma, (1, 13), (6, 27), (6, 29))}}


@contextmanager
def leitura(pasta, caminho):
    s = RT.abrir(pasta, caminho, com_ct=False)
    try:
        yield s
    finally:
        s.fechar()


class Motor89(unittest.TestCase):
    def test_particao_em_l2_sem_voxel_novo(self):
        forma = (12, 14, 16)
        for sentido in (("sup", "post", "esq"), ("inf", "post", "dir"),
                        ("post", "sup", "esq"), ("post", "esq", "inf")):
            with self.subTest(sentido=sentido):
                g = G.Grade((2.5, 1.3, 0.8), sentido)
                cord = caixa(forma, (1, 11), (3, 12), (4, 13))
                l2 = caixa(forma, (5, 7), (6, 8), (7, 9))
                antes = cord.copy()
                a, b, info = E.partir_medula_em_l2(cord, l2, g)
                self.assertTrue(np.array_equal(a | b, antes))
                self.assertFalse((a & b).any())
                self.assertTrue(np.array_equal(cord, antes))
                corte = [slice(None)] * 3
                corte[info["eixo"]] = info["corte"]
                self.assertTrue(np.array_equal(b[tuple(corte)], antes[tuple(corte)]))
                self.assertNotIn("spinal_cord", E.DERIVADAS)

    def test_residuo_exige_duas_mascaras_e_preserva_heart(self):
        forma = (8, 16, 16)
        heart = caixa(forma, (2, 6), (5, 11), (5, 11))
        modelo = caixa(forma, (1, 7), (4, 12), (4, 12))
        ga = caixa(forma, (1, 7), (2, 4), (2, 4))
        d = {"heart": heart.copy(), "heart_model": modelo, "great_arteries": ga}
        obs = {"great_arteries": "Margem engolida pela grade; revisar."}
        ctx = E.acabamentos_terminais(d, G.Grade((1, 1, 1)), observacoes=obs)
        self.assertTrue(np.array_equal(d["great_arteries"], ga | (modelo & ~heart)))
        self.assertTrue(np.array_equal(d["heart"], heart))
        self.assertIn("arterias", ctx)
        self.assertTrue(obs["great_arteries"].startswith("Margem engolida"))
        E.acabamentos_terminais(d, G.Grade((1, 1, 1)), observacoes=obs)
        self.assertEqual(obs["great_arteries"].count("GreatArteries:"), 1)
        for defeito in ({"heart_model": modelo}, {"heart": heart},
                        {"heart_model": modelo, "heart": np.zeros_like(heart)},
                        {"heart_model": modelo, "heart": np.ones((2, 3, 4), bool)}):
            defeito["great_arteries"] = ga.copy()
            linhas = []
            c = E.acabamentos_terminais(defeito, G.Grade((1, 1, 1)), log=linhas.append)
            self.assertNotIn("arterias", c)
            self.assertTrue(np.array_equal(defeito["great_arteries"], ga))
            self.assertTrue(linhas)

    def test_sem_l2_preserva_medula_e_registra(self):
        cord = np.ones((5, 8, 8), bool)
        d, linhas = {"spinal_cord": cord.copy()}, []
        E.acabamentos_terminais(d, G.Grade((1, 1, 1)), log=linhas.append)
        self.assertTrue(np.array_equal(d["spinal_cord"], cord))
        self.assertNotIn("cauda_equina", d)
        self.assertTrue(any("sem L2" in x for x in linhas))

    def serie(self, sagital=False):
        base = _cleanup.temporaria("radai_motor89_serie_")
        pasta = os.path.join(base, "serie")
        with patch.object(MS, "ROWS", 32), patch.object(MS, "COLS", 36):
            MS.escreve_serie(pasta, "FANTOMA_MOTOR_89", datetime(2026, 1, 1), 14)
        if sagital:
            for i, caminho in enumerate(sorted(Path(pasta).glob("*.dcm"))):
                ds = pydicom.dcmread(caminho)
                ds.ImageOrientationPatient = [0, 1, 0, 0, 0, -1]
                ds.ImagePositionPatient = [-i * float(ds.SliceThickness), -18, 16]
                ds.save_as(caminho, enforce_file_format=True)
        img = E.load_sitk(pasta)
        import SimpleITK as sitk
        return pasta, G.Grade.de_sitk(img), sitk.GetArrayFromImage(img)

    def gravar(self, pasta, g, vol, masks, suave=0, modo=None):
        meta = {"devolver_mascaras": True}
        spec = {"heart": {"suavizar_mm": 0.0, "recortar_por": (), "contem": ()}}
        gravar = ({"heart", "great_arteries", "spinal_cord", "cauda_equina"}
                  if modo == "fast" else None)
        caminho, nomes = E.build_rtstruct(
            pasta, masks, rotulo="RadAI_FULL" if modo is None else None,
            serie=(g, np.full(vol.shape, 40, np.int16)), externo=np.ones(vol.shape, bool),
            modalidade="CT", suavizar_mm=suave, construcoes=spec,
            exigir_grade=True, meta=meta, modo=modo, gravar=gravar,
            compostos_inteiros=modo == "fast", decimar_mm=0.2 if modo == "fast" else None)
        return caminho, nomes, meta

    def test_dicom_arterias_e_particao_apos_taubin(self):
        cenas = [(s, v, m, t) for t in ("eclipse", "monaco")
                 for s, v, m in ((False, 0, None), (False, 1.0, "fast"),
                                  (True, 1.0, None))]
        for sagital, suave, modo, tps in cenas:
            with self.subTest(sagital=sagital, suave=suave, modo=modo, tps=tps), \
                 patch.dict(os.environ, {"RADAI_TPS_DESTINO": tps}):
                pasta, g, vol = self.serie(sagital)
                f = vol.shape
                heart = caixa(f, (3, 11), (9, 23), (9, 24))
                modelo = caixa(f, (2, 12), (7, 25), (7, 26))
                ga = caixa(f, (2, 12), (3, 6), (3, 6))
                cord = caixa(f, (1, 13), (13, 18), (27, 32))
                l2 = caixa(f, (6, 8), (16, 19), (27, 31))
                d = {"heart": heart, "heart_model": modelo, "great_arteries": ga,
                     "spinal_cord": cord, "vertebrae_L2": l2}
                with patch.object(E, "acabamentos_terminais", return_value={}):
                    anterior, _n, _m = self.gravar(pasta, g, vol, d, suave, None)
                with leitura(pasta, anterior) as s:
                    antes_cord = s.mascara_de("spinal_cord").copy()
                    antes_heart = s.mascara_de("heart").copy()
                    antes_ga = s.mascara_de("great_arteries").copy()
                    antes_modelo = s.mascara_de("heart_model").copy()
                laudos = []
                gravar = E.gravar_rtstruct
                def conferir_gravacao(*a, **kw):
                    r = gravar(*a, **kw)
                    laudos.append(r)
                    return r
                with patch.object(E, "gravar_rtstruct", side_effect=conferir_gravacao):
                    caminho, nomes, meta = self.gravar(pasta, g, vol, d, suave, modo)
                if tps == "monaco":
                    self.assertGreater(laudos[-1]["furos"], 0)
                with leitura(pasta, caminho) as s:
                    a = s.mascara_de("spinal_cord")
                    b = s.mascara_de("cauda_equina")
                    self.assertFalse((a & b).any())
                    self.assertTrue(np.array_equal(a | b, antes_cord))
                    if modo != "fast":
                        aa, bb, _info = E.partir_medula_em_l2(
                            antes_cord, s.mascara_de("vertebrae_L2"), s.grade)
                        self.assertTrue(np.array_equal(a, aa))
                        self.assertTrue(np.array_equal(b, bb))
                    esperado = meta["acabamento_terminal"]["cauda_equina"]
                    self.assertEqual(esperado["dsc_uniao"], 1.0)
                    self.assertEqual(esperado["voxels_novos"], 0)
                    self.assertEqual(esperado["voxels_perdidos"], 0)
                    ar = s.mascara_de("great_arteries")
                    h = s.mascara_de("heart")
                    self.assertTrue(ar.any())
                    self.assertTrue(np.array_equal(h, antes_heart))
                    if modo != "fast":
                        hm = s.mascara_de("heart_model")
                        self.assertFalse(((hm & ~h) & ~ar).any())
                        self.assertTrue(np.array_equal(ar, antes_ga | (antes_modelo & ~antes_heart)))
                    self.assertFalse(any(n.startswith("_RadAI_insumo") for n in s.nomes))
                ds = pydicom.dcmread(caminho)
                self.assertEqual(ds.ApprovalStatus, "UNAPPROVED")
                ce = next(r for r in ds.StructureSetROISequence if str(r.ROIName) == nomes["cauda_equina"])
                self.assertIn("derivada", str(ce.ROIGenerationDescription))
                if modo != "fast":
                    self.assertIn("L2", str(ce.ROIDescription))
                else:
                    obs = next(o.ROIObservationDescription for o in ds.RTROIObservationsSequence
                               if int(o.ReferencedROINumber) == int(ce.ROINumber))
                    self.assertIn("L2", obs)
                _cleanup.apagar_arvore(str(Path(caminho).parent))
                _cleanup.apagar_arvore(str(Path(anterior).parent))

    def test_particao_dicom_com_parte_vazia_ou_menor_que_dez_voxels(self):
        for pos in (0, 6, 13):
            with self.subTest(pos=pos):
                pasta, g, vol = self.serie()
                cord = caixa(vol.shape, (1, 13), (15, 16), (15, 16))
                l2 = caixa(vol.shape, (pos, pos + 1), (14, 17), (17, 20))
                with patch.object(E, "acabamentos_terminais", return_value={}):
                    anterior, _n, _m = self.gravar(pasta, g, vol, {"spinal_cord": cord}, 0)
                with leitura(pasta, anterior) as s:
                    antes = s.mascara_de("spinal_cord").copy()
                caminho, _n, meta = self.gravar(pasta, g, vol,
                    {"spinal_cord": cord, "vertebrae_L2": l2}, 0)
                with leitura(pasta, caminho) as s:
                    a = s.mascara_de("spinal_cord") if s.resolver("spinal_cord") else np.zeros_like(antes)
                    b = s.mascara_de("cauda_equina") if s.resolver("cauda_equina") else np.zeros_like(antes)
                    self.assertTrue(np.array_equal(a | b, antes))
                    self.assertFalse((a & b).any())
                    self.assertEqual(meta["acabamento_terminal"]["cauda_equina"]["dsc_uniao"], 1.0)
                _cleanup.apagar_arvore(str(Path(caminho).parent))
                _cleanup.apagar_arvore(str(Path(anterior).parent))

    def test_fast_cranio_no_dicom_sem_construir_pele_ou_parede(self):
        pasta, g, vol = self.serie()
        f = vol.shape
        brain = caixa(f, (1, 13), (5, 27), (5, 31))
        stem = caixa(f, (2, 11), (13, 20), (14, 21))
        chiasm = caixa(f, (8, 10), (10, 14), (13, 23))
        rib = caixa(f, (1, 13), (2, 3), (2, 26))
        cruas = {"total_v3": {"brain": brain, "rib_left_1": rib,
                               "sternum": rib.copy(), "costal_cartilages": rib.copy()}}
        extras = {"orgaos": {"brain_brainstem": stem, "optic_chiasm": chiasm,
                              "brain_ventricles": brain.copy()},
                  "origem": {"brain_brainstem": "cranio_ct", "optic_chiasm": "cranio_ct"}}
        base = _cleanup.temporaria("radai_motor89_fast_")
        sd = RO.Saida(E, pasta, base, "RS_FANTOMA.dcm", tasks=["total_v3"],
                      versao="teste", suavizar_mm=1.0, modalidade="CT")
        sd.devolver_mascaras = True
        individuais = E._suavizar_individuais
        vistas = []
        def conferir(m, nomes, *args, **kw):
            vistas.extend(nomes)
            return individuais(m, nomes, *args, **kw)
        import radai_skin
        with patch.object(radai_skin, "pele", side_effect=AssertionError("Skin dispensavel")) as sk, \
             patch.object(radai_skin, "parede_toracica", side_effect=AssertionError("parede dispensavel")) as cw, \
             patch.object(E, "_suavizar_individuais", side_effect=conferir):
            r = sd.full_e_oar(cruas, volume_hu=np.full(f, 40, np.int16),
                              modo="fast", extras=extras)
            sk.assert_not_called()
            cw.assert_not_called()
        self.assertIsNone(r.get("full"))
        ds = pydicom.dcmread(r["oar_fast"])
        nomes = {str(x.ROIName) for x in ds.StructureSetROISequence}
        self.assertIn("Brainstem_ai", nomes)
        self.assertIn("OpticChiasm_ai", nomes)
        self.assertFalse(any(n.startswith(("Skin", "ChestWall", "Rib", "CostalCartilages", "Ventricles")) for n in nomes))
        self.assertFalse(any(n.startswith(("rib_", "ribs_", "costal_cartilages")) for n in vistas))

    def test_tmj_terminal_no_dicom_e_limite_original_na_spec(self):
        import radai_constructs as C
        import radai_skin as SK
        c = C.Construcao("tmj_left", np.ones((6, 8, 8), bool), "teste",
                         extras={"limite_inferior_canonico": 3})
        with patch.object(C, "atms", return_value={"tmj_left": c}):
            saida = E._construir_atms({}, G.Grade((1, 1, 1)))
        self.assertEqual(saida.especificacoes["tmj_left"]["limite_inferior_canonico"], 3)
        for sagital in (False, True):
            pasta, g, vol = self.serie(sagital)
            m = caixa(vol.shape, (2, 12), (7, 23), (8, 23))
            spec = {"tmj_left": {"suavizar_mm": 0.0, "recortar_por": (),
                                  "limite_inferior_canonico": 10}}
            caminho, _nomes = E.build_rtstruct(pasta, {"tmj_left": m},
                serie=(g, np.full(vol.shape, 40, np.int16)), externo=np.ones(vol.shape, bool),
                modalidade="CT", suavizar_mm=1.0, construcoes=spec, exigir_grade=True)
            with leitura(pasta, caminho) as s:
                final = s.mascara_de("tmj_left")
                self.assertFalse(SK._para_canonico(final, g)[:10].any())
            _cleanup.apagar_arvore(str(Path(caminho).parent))

    def test_heart_fast_igual_a_referencia_publicada_88(self):
        referencias = {
            0: "c4982515a03885ade107df5043fd71e03d249840daba67d8612440044cd7b798",
            3: "73859d16ad7271f3640afa2f4067cf3907e5b68f4981a63f8dd39a239110966b",
            10: "309f7f8474c41017539090143b82b5b34c100711ad0cba29ebee5ef83abfc935"}
        for variante, esperado in referencias.items():
            with self.subTest(variante=variante):
                pasta, g, vol = self.serie()
                base = _cleanup.temporaria("radai_motor89_heart_")
                sd = RO.Saida(E, pasta, base, "RS_FANTOMA89.dcm",
                              tasks=["total_v3", "trunk_cavities"],
                              versao="teste89", suavizar_mm=1.0, modalidade="CT")
                refeitas, individuais = [], []
                recompor, suavizar = E.recompor_compostos, E._suavizar_individuais
                def recompostas(*a, **kw):
                    r = recompor(*a, **kw)
                    refeitas.extend(r)
                    return r
                def suavizadas(m, nomes, *a, **kw):
                    individuais.extend(nomes)
                    return suavizar(m, nomes, *a, **kw)
                with patch.object(E, "VOLUME_MINIMO_CORACAO_CM3", 1.0), \
                     patch.object(E, "recompor_compostos", side_effect=recompostas), \
                     patch.object(E, "_suavizar_individuais", side_effect=suavizadas):
                    r = sd.full_e_oar(cruas_cardiacas(vol.shape, variante),
                                      volume_hu=np.full(vol.shape, 40, np.int16), modo="fast")
                self.assertFalse(any(n.startswith("ribs_") for n in refeitas))
                self.assertFalse(any(n.startswith(("rib_", "ribs_")) for n in individuais))
                with leitura(pasta, r["oar_fast"]) as s:
                    heart = s.mascara("Heart_ai")
                    self.assertEqual(hashlib.sha256(heart.tobytes()).hexdigest(), esperado)
                    self.assertFalse(any(n.startswith(("Skin", "ChestWall", "Rib", "CostalCartilages")) for n in s.nomes))

    def test_cauda_nome_cor_e_procedencia_no_fast(self):
        import radai_config as cfg
        import radai_sets as sets
        pasta, g, vol = self.serie()
        cord = caixa(vol.shape, (1, 13), (14, 19), (14, 20))
        l2 = caixa(vol.shape, (6, 8), (12, 22), (21, 27))
        with patch.object(cfg, "ler_nomes", return_value={"modo": "proprios",
                "nomes": {"CaudaEquina_ai": "CaudaServico"},
                "cores": {"CaudaEquina_ai": [7, 83, 191]}}):
            caminho, nomes = E.build_rtstruct(pasta,
                {"spinal_cord": cord, "vertebrae_L2": l2},
                serie=(g, np.full(vol.shape, 40, np.int16)), externo=np.ones(vol.shape, bool),
                modalidade="CT", suavizar_mm=1.0, exigir_grade=True,
                gravar={"spinal_cord", "cauda_equina"}, modo="fast",
                nomes_do_entregue={"CaudaEquina_ai": "CaudaServico"})
        self.assertEqual(nomes["cauda_equina"], "CaudaServico")
        ds = pydicom.dcmread(caminho)
        roi = next(r for r in ds.StructureSetROISequence if str(r.ROIName) == "CaudaServico")
        self.assertEqual(sets.nome_padrao_da_descricao(roi.ROIDescription), "CaudaEquina_ai")
        self.assertIn("derivada", roi.ROIGenerationDescription)
        cor = next(r.ROIDisplayColor for r in ds.ROIContourSequence
                   if int(r.ReferencedROINumber) == int(roi.ROINumber))
        self.assertEqual(tuple(cor), (7, 83, 191))
        obs = next(o.ROIObservationDescription for o in ds.RTROIObservationsSequence
                   if int(o.ReferencedROINumber) == int(roi.ROINumber))
        self.assertIn("L2", obs)
        with leitura(pasta, caminho) as s:
            self.assertEqual(s.resolver("cauda_equina"), "CaudaServico")
        _cleanup.apagar_arvore(str(Path(caminho).parent))


if __name__ == "__main__":
    unittest.main(verbosity=2)
