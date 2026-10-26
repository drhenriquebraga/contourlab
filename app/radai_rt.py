# -*- coding: utf-8 -*-
import os
import tempfile

import numpy as np
import pydicom

import radai_geom

VERSAO_RT = "1.0"

_ENGINE = None


def _motor():
    global _ENGINE
    if _ENGINE is None:
        import engine
        _ENGINE = engine
    return _ENGINE


def fatias_da_serie(pasta, uid=None, modalidades=None):
    if modalidades is None:
        # GUARDA: sem o UID, TC e RM da mesma pasta virariam uma serie so.
        modalidades = ("CT", "MR") if uid else ("CT",)
    achados = []
    for raiz, dirs, arquivos in os.walk(str(pasta)):
        dirs[:] = [d for d in dirs if d != "_RadAI"]
        for nome in arquivos:
            fp = os.path.join(raiz, nome)
            try:
                ds = pydicom.dcmread(fp, stop_before_pixels=True, force=True,
                                     specific_tags=["SeriesInstanceUID", "Modality"])
            except Exception:
                continue
            if str(getattr(ds, "Modality", "")).upper() not in modalidades:
                continue
            if uid and str(getattr(ds, "SeriesInstanceUID", "")) != str(uid):
                continue
            achados.append(fp)
    return achados


class SessaoRT(object):

    def __init__(self, pasta_limpa, caminho_rs, grade, forma, nomes, rt, ct=None, teto=6):
        self.pasta_limpa = pasta_limpa
        self.caminho_rs = caminho_rs
        self.grade = grade
        self.forma = forma
        self.nomes = list(nomes)
        self.ct = ct
        self._rt = rt
        self._cache = {}
        self._ordem = []
        self.teto = teto

    def mascara(self, nome):
        if nome in self._cache:
            return self._cache[nome]
        if nome not in self.nomes:
            raise KeyError("estrutura %r nao esta no RTSTRUCT (tem: %s)"
                           % (nome, ", ".join(self.nomes)))
        bruta = self._mascara_bruta(nome)
        m = np.ascontiguousarray(np.transpose(np.asarray(bruta, dtype=bool), (2, 0, 1)))
        if m.shape != self.forma:
            raise ValueError("mascara de %r com forma %r; o CT e %r"
                             % (nome, m.shape, self.forma))
        self._cache[nome] = m
        self._ordem.append(nome)
        while len(self._ordem) > self.teto:
            self._cache.pop(self._ordem.pop(0), None)
        return m

    SUB = 8

    def _mascara_bruta(self, nome):
        import cv2
        from rt_utils import image_helper as _ih
        roi = None
        for r in getattr(self._rt.ds, "ROIContourSequence", []):
            num = int(getattr(r, "ReferencedROINumber", -1))
            for s in getattr(self._rt.ds, "StructureSetROISequence", []):
                if int(getattr(s, "ROINumber", -2)) == num and \
                        str(getattr(s, "ROIName", "")) == nome:
                    roi = r
                    break
            if roi is not None:
                break
        if roi is None:
            return self._rt.get_roi_mask_by_name(nome)

        serie = self._rt.series_data
        mtx = _ih.get_patient_to_pixel_transformation_matrix(serie)
        nz, ny, nx = self.forma
        saida = np.zeros((ny, nx, nz), dtype=bool)
        normal = _ih.get_slice_directions(serie[0])[2]
        zs = [float(np.dot(normal, [float(v) for v in s.ImagePositionPatient]))
              for s in serie]
        K = int(self.SUB)
        for c in getattr(roi, "ContourSequence", None) or []:
            dados = [float(v) for v in (getattr(c, "ContourData", None) or [])]
            if len(dados) < 9 or len(dados) % 3:
                continue
            pts = np.reshape(dados, (-1, 3))
            w = float(np.dot(normal, pts[0]))
            k = int(np.argmin([abs(z - w) for z in zs]))
            px = _ih.apply_transformation_to_3d_points(pts, mtx)[:, :2]
            x0 = max(0, int(np.floor(px[:, 0].min())))
            x1 = min(nx - 1, int(np.ceil(px[:, 0].max())))
            y0 = max(0, int(np.floor(px[:, 1].min())))
            y1 = min(ny - 1, int(np.ceil(px[:, 1].max())))
            if x1 < x0 or y1 < y0:
                continue
            w, h = x1 - x0 + 1, y1 - y0 + 1
            fino = np.zeros((h * K, w * K), dtype=np.uint8)
            q = np.round((px - np.array([x0, y0])) * K).astype(np.int32)
            cv2.fillPoly(fino, [q], 1)
            recorte = fino[::K, ::K].astype(bool)
            saida[y0:y1 + 1, x0:x1 + 1, k] ^= recorte
        return saida

    def _por_nome_padrao(self):
        if getattr(self, "_padroes", None) is None:
            self._padroes = {}
            try:
                import radai_sets
                for s in (getattr(self._rt.ds, "StructureSetROISequence", None)
                          or []):
                    n = str(getattr(s, "ROIName", ""))
                    p = radai_sets.nome_padrao_da_descricao(
                        getattr(s, "ROIDescription", ""))
                    if p and n and p != n:
                        self._padroes.setdefault(p, n)
            except Exception:
                self._padroes = {}
        return self._padroes

    def resolver(self, chave, sufixo="_ai"):
        if not chave:
            return None
        if chave in self.nomes:
            return chave
        # GUARDA: no STUDY com nome proprio, o nome padrao mora na descricao.
        proprio = self._por_nome_padrao().get(str(chave))
        if proprio in self.nomes:
            return proprio
        alvo = str(chave)
        try:
            esperado = _motor().nome_clinico(alvo, sufixo=sufixo)
            if esperado in self.nomes:
                return esperado
            proprio = self._por_nome_padrao().get(esperado)
            if proprio in self.nomes:
                return proprio
        except Exception:
            pass

        def raiz(n):
            try:
                import radai_sets
                return radai_sets.raiz_sem_sufixo(n)
            except Exception:
                pass
            t = str(n).lower()
            for s in ("_ai", "_v3d"):
                if t.endswith(s):
                    t = t[:-len(s)]
                    break
            for longo, curto in (("_left", "_l"), ("_right", "_r")):
                if t.endswith(longo):
                    t = t[:-len(longo)] + curto
                    break
            return t.replace("_", "")

        r = raiz(alvo)
        candidatos = [n for n in self.nomes
                      if raiz(n) == r or (len(r) >= 5 and r.startswith(raiz(n)))
                      or (len(raiz(n)) >= 5 and raiz(n).startswith(r))]
        preferidos = [n for n in candidatos if n.lower().endswith(sufixo.lower())]
        for lista in (preferidos, candidatos):
            if len(lista) == 1:
                return lista[0]
        return None

    def mascara_de(self, chave, sufixo="_ai"):
        nome = self.resolver(chave, sufixo)
        if nome is None:
            raise KeyError(
                "nao achei %r no RTSTRUCT (nem como nome clinico). "
                "O arquivo tem %d estruturas; as primeiras: %s"
                % (chave, len(self.nomes), ", ".join(self.nomes[:8])))
        return self.mascara(nome)

    def contexto(self, nomes=None):
        alvo = self.nomes if nomes is None else [n for n in nomes if n in self.nomes]
        return {"grade": self.grade, "forma": self.forma,
                "estruturas": dict((n, self.mascara(n)) for n in alvo)}

    def fechar(self):
        import shutil
        try:
            shutil.rmtree(str(self.pasta_limpa), ignore_errors=True)
        except Exception:
            pass
        self._cache.clear()
        del self._ordem[:]


def abrir(pasta_serie, caminho_rs, uid=None, com_ct=True):
    from rt_utils import RTStructBuilder

    arquivos = fatias_da_serie(pasta_serie, uid)
    if not arquivos:
        raise ValueError("nenhuma imagem %s encontrada em %s"
                         % ("da serie " + str(uid) if uid else "CT", pasta_serie))
    engine = _motor()
    stage = tempfile.mkdtemp(prefix="radai_calib_")
    engine.copy_sorted(arquivos, stage)
    imagem = engine.load_sitk(stage)
    grade = radai_geom.Grade.de_sitk(imagem)
    forma = tuple(int(v) for v in reversed(imagem.GetSize()))
    rt = RTStructBuilder.create_from(dicom_series_path=stage,
                                     rt_struct_path=str(caminho_rs), warn_only=True)
    ct = None
    if com_ct:
        import SimpleITK as sitk
        ct = sitk.GetArrayFromImage(imagem).astype(np.int16, copy=False)
    return SessaoRT(stage, str(caminho_rs), grade, forma, rt.get_roi_names(), rt, ct=ct)


def abrir_ct(pasta_serie, uid=None):
    import SimpleITK as sitk

    arquivos = fatias_da_serie(pasta_serie, uid)
    if not arquivos:
        raise ValueError("nenhuma imagem %s encontrada em %s"
                         % ("da serie " + str(uid) if uid else "CT", pasta_serie))
    engine = _motor()
    stage = tempfile.mkdtemp(prefix="radai_ct_")
    engine.copy_sorted(arquivos, stage)
    imagem = engine.load_sitk(stage)
    grade = radai_geom.Grade.de_sitk(imagem)
    forma = tuple(int(v) for v in reversed(imagem.GetSize()))
    ct = sitk.GetArrayFromImage(imagem).astype(np.int16, copy=False)
    return SessaoRT(stage, "", grade, forma, [], None, ct=ct)


def medir_ciclo(original, devolvida, grade):
    m = radai_geom.metricas(devolvida, original, grade)
    m["centroide_z_original"] = _centroide_z(original)
    m["centroide_z_devolvida"] = _centroide_z(devolvida)
    m["desloc_z_voxels"] = (None if None in (m["centroide_z_original"],
                                             m["centroide_z_devolvida"])
                            else round(abs(m["centroide_z_devolvida"]
                                           - m["centroide_z_original"]), 3))
    m["fatias_original"] = int(np.count_nonzero(np.any(original, axis=(1, 2))))
    m["fatias_devolvida"] = int(np.count_nonzero(np.any(devolvida, axis=(1, 2))))
    return m


def _centroide_z(mask):
    zs = np.where(np.any(np.asarray(mask, dtype=bool), axis=(1, 2)))[0]
    return None if zs.size == 0 else float(zs.mean())
