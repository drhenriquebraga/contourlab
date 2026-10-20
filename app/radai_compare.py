# -*- coding: utf-8 -*-
import os
import tempfile
import time

import radai_archive
import radai_geom
import radai_terms

VERSAO_COMPARAR = "1.0"


def _motor():
    import engine
    return engine


def rodar_para_entrega(pasta_limpa, forma, grade, uid, masks_nossas, pasta_serie="",
                       rs_nome="", ident="nv_segment_ct", python_exe=None, log=None,
                       timeout_s=7200, registrar=True):
    import radai_nv_engine as vm
    resumo = {"uid": uid, "classes": 0, "comparadas": 0, "erro": "",
              "avisos": [], "segundos": 0.0, "arquivo": ""}
    t0 = time.time()
    trabalho = None
    try:
        classes = vm.classes(ident)
        trabalho = tempfile.mkdtemp(prefix="radai_v3d_")
        nifti = vm.para_nifti(pasta_limpa, os.path.join(trabalho, "ct.nii.gz"))
        ids = vm.ids_permitidos(ident)
        if log:
            log("VISTA-3D: %d classes numa chamada (uma so por serie)" % len(ids))
        saida = vm.rodar(nifti, ident=ident, label_prompt=ids,
                         timeout_s=timeout_s, python_exe=python_exe, log=log)

        guardado = ""
        try:
            import shutil
            destino = radai_archive.pasta_nv(criar=True) / ("%s.nii.gz" % uid)
            tmp = destino.with_name(destino.name + ".parcial")
            shutil.copy2(saida, str(tmp))
            os.replace(str(tmp), str(destino))
            guardado = str(destino)
            saida = guardado
        except Exception as e:
            resumo["avisos"].append("nao guardei a saida do VISTA-3D (%s): a "
                                    "conferencia nao vai redesenhar o contorno dele" % e)
        resumo["arquivo"] = guardado

        nv = masks_do_nv(saida, forma, classes, log=log)
        resumo["classes"] = len(nv)
        if registrar:
            resumo["comparadas"] = _enfileirar(
                uid, masks_nossas, nv, classes, grade, pasta_serie, rs_nome,
                guardado, resumo)
        return nv, resumo
    except Exception as e:
        resumo["erro"] = "%s: %s" % (type(e).__name__, str(e)[:250])
        return {}, resumo
    finally:
        resumo["segundos"] = round(time.time() - t0, 1)
        if trabalho:
            import shutil
            shutil.rmtree(trabalho, ignore_errors=True)


def _enfileirar(uid, masks_nossas, nv, classes, grade, pasta_serie, rs_nome,
                arquivo, resumo):
    ids_por_chave = nv.ids()
    nome_por_chave = dict(
        (c, c[len(_motor().PREFIXO_NV):]) for c in ids_por_chave)
    cruzamento = radai_terms.comparaveis(
        list(masks_nossas), [n for n in classes])
    n = 0
    for c in cruzamento:
        try:
            nossa = masks_nossas.get(c["ts"])
            if nossa is None:
                continue
            chaves = [k for k, nome in nome_por_chave.items()
                      if nome in [radai_terms.normalizar(v) for v in c["nv"]]]
            if not chaves:
                continue
            uniao = None
            for k in chaves:
                m = nv[k]
                uniao = m if uniao is None else (uniao | m)
            met = radai_geom.metricas(uniao, nossa, grade)
            radai_archive.registrar_comparacao(
                uid=uid, estrutura=c["ts"], ts_nome=c["ts"],
                nv_nome=" + ".join(c["nv"]), metricas=met,
                relacao=c["relacao"], pasta=str(pasta_serie), rs=rs_nome,
                nv_arquivo=arquivo,
                nv_ids=[ids_por_chave[k] for k in chaves],
                avisos=([c.get("nota")] if c.get("nota") else []))
            n += 1
            del uniao
        except Exception as e:
            resumo["avisos"].append("comparacao de %s falhou: %s"
                                    % (c["ts"], str(e)[:120]))
    return n


class MascarasDoNV(object):

    def __init__(self, saida, forma, por_chave):
        self.saida = saida
        self.forma = forma
        self._por_chave = dict(por_chave)

    def __iter__(self):
        return iter(self._por_chave)

    def __len__(self):
        return len(self._por_chave)

    def __contains__(self, chave):
        return chave in self._por_chave

    def keys(self):
        return self._por_chave.keys()

    def __getitem__(self, chave):
        import radai_nv_engine as vm
        return vm.ler_saida(self.saida, self.forma, rotulo=self._por_chave[chave])

    def items(self):
        for k in self._por_chave:
            yield k, self[k]

    def ids(self):
        return dict(self._por_chave)


def masks_do_nv(saida, forma, classes_nv, minimo_voxels=10, log=None):
    import radai_nv_engine as vm
    presentes = vm.rotulos_da_saida(saida)
    por_id = dict((i, n) for n, i in classes_nv.items())
    por_chave, vazias = {}, 0
    for ident_classe, quantos in sorted(presentes.items()):
        if ident_classe in (0, vm.NAO_AVALIADO):
            continue
        if quantos < minimo_voxels:
            vazias += 1
            continue
        nome = por_id.get(ident_classe)
        if not nome:
            continue
        chave = "%s%s" % (_motor().PREFIXO_NV, radai_terms.normalizar(nome))
        por_chave[chave] = ident_classe
    if log and vazias:
        log("VISTA-3D: %d classe(s) com menos de %d voxels, nao incluidas "
            "no estudo comparativo" % (vazias, minimo_voxels))
    return MascarasDoNV(saida, forma, por_chave)


