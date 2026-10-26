# -*- coding: utf-8 -*-
import hashlib
import io
import os
import shutil
import sys
import tempfile
import types

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "app"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import _cleanup
import _componentes
_cleanup.adotar_prefixo("radai_teste_md5_")
_cleanup.adotar_prefixo("radai_teste_req_")
os.environ["RADAI_CALIB_DIR"] = tempfile.mkdtemp(prefix="radai_ac_modelos_")
_cleanup.adotar_prefixo("radai_ac_modelos_")

_R = []


def checar(nome, ok, detalhe=""):
    _R.append((nome, bool(ok), detalhe))
    print("  %s  %s%s" % ("OK   " if ok else "FALHA", nome,
                          ("  [%s]" % detalhe) if detalhe else ""))
    return bool(ok)


def secao(t):
    print(u"\n  ── %s ─────────────────────────" % t)


def ler(rel):
    return io.open(_componentes.fonte(rel), encoding="utf-8").read()


class _Grade(object):
    def __init__(self, spacing=(2.0, 1.0, 1.0),
                 sentido=("sup", "post", "esq")):
        import radai_geom
        self._g = radai_geom.Grade(spacing, sentido)
        self.spacing = self._g.spacing
        self.sentido = self._g.sentido

    def eixo_sinal(self, lado):
        return self._g.eixo_sinal(lado)

    @property
    def volume_voxel_mm3(self):
        return self._g.volume_voxel_mm3


def teste_o_registro_tem_o_do_cranio():
    secao(u"o registro dos modelos tem o do encéfalo, livre e com digest")
    import radai_models as M
    for ident in ("cranio_buti",):
        m = M.MODELOS.get(ident) or {}
        checar(u"`%s` está no registro" % ident, bool(m))
        checar(u"  e é de uso livre", m.get("uso_permitido") == "livre",
               m.get("uso_permitido"))
        dig = dict(m.get("sha256") or {})
        dig.update(m.get("md5") or {})
        checar(u"  e todo arquivo baixado tem digest",
               all(rel in dig for rel, _t in (m.get("arquivos") or ())),
               str([r for r, _ in m.get("arquivos") or ()]))
        checar(u"  e todo tamanho é medido (inteiro, sem arredondar)",
               all(isinstance(t, int) and t > 0
                   for _r, t in (m.get("arquivos") or ())))
        e = M.estado_do_modelo(ident)
        checar(u"  e o estado diz que é baixável", e.get("baixavel"), str(e))


def teste_a_url_do_hugging_face_e_fixa():
    secao(u"o Hugging Face na revisão fixa (hash fixo exige origem imutável)")
    import radai_models as M
    m = M.MODELOS["cranio_buti"]
    rel = m["arquivos"][-1][0]
    url = M.url_do_arquivo(m, rel)
    checar(u"a URL do peso aponta a revisão", m["revisao"] in url, url)
    checar(u"  e não o `main`", "/resolve/main/" not in url, url)
    isca = dict(m)
    isca.pop("revisao")
    checar(u"  (isca) sem a revisão a URL cai no `main`",
           "/resolve/main/" in M.url_do_arquivo(isca, rel))
    checar(u"o checkpoint traz o hash que o Hugging Face publica (LFS)",
           m["sha256"][rel].startswith("d098f10fd812"))


def teste_o_md5_reprova_o_arquivo_trocado():
    secao(u"o md5 publicado pelo Zenodo reprova o download trocado")
    import radai_models as M
    d = tempfile.mkdtemp(prefix="radai_teste_md5_")
    try:
        fonte = os.path.join(d, "fonte.bin")
        with open(fonte, "wb") as f:
            f.write(b"peso de verdade" * 100)
        certo = hashlib.md5(open(fonte, "rb").read()).hexdigest()
        url = "file:///" + fonte.replace("\\", "/")
        from pathlib import Path
        alvo = Path(d) / "alvo.bin"
        M._baixar_arquivo(url, alvo, os.path.getsize(fonte), "x", "alvo.bin",
                          md5_esperado=certo)
        checar(u"com o md5 certo o arquivo fica", alvo.is_file())
        alvo.unlink()
        try:
            M._baixar_arquivo(url, alvo, os.path.getsize(fonte), "x",
                              "alvo.bin", md5_esperado="0" * 32)
            reprovou = False
        except IOError:
            reprovou = True
        checar(u"com o md5 errado ele LEVANTA", reprovou)
        checar(u"  e não deixa nada no disco (nem o .parcial)",
               not alvo.exists()
               and not (Path(d) / "alvo.bin.parcial").exists())
        M._baixar_arquivo(url, alvo, os.path.getsize(fonte), "x", "alvo.bin",
                          md5_esperado=None)
        checar(u"  (isca) sem md5 declarado o mesmo arquivo passa",
               alvo.is_file())
    finally:
        shutil.rmtree(d, ignore_errors=True)


def teste_o_registro_aceita_o_par_original_e_enxuto():
    secao(u"o registro aceita o checkpoint original e o enxuto (sem o "
          u"estado do otimizador)")
    import re
    import radai_models as M
    from pathlib import Path
    esperado = {"hnlnl": 10, "cranio_buti": 1, "moose": 4, "cads_open": 1}
    for ident, n in sorted(esperado.items()):
        m = M.MODELOS[ident]
        enx = m.get("enxuto") or {}
        checar(u"%s declara o enxuto de %d checkpoint(s)" % (ident, n),
               len(enx) == n, str(sorted(enx)))
        checar(u"  cada um com bytes inteiros e sha256 de 64 hexa",
               all(isinstance(b, int) and b > 0
                   and re.match(r"^[0-9a-f]{64}$", s or "")
                   for b, s in enx.values()))
        orig = dict(m.get("arquivos") or ())
        orig.update(dict(m.get("conteudo") or ()))
        checar(u"  e menor que o original onde o registro mede o original",
               all(enx[r][0] < orig[r] for r in enx if r in orig))
    hn = M.MODELOS["hnlnl"]
    checar(u"no hnlnl, os dez checkpoints do conteúdo têm o enxuto",
           set(hn["enxuto"]) == set(r for r, _t in hn["conteudo"]
                                    if r.endswith(".model")))
    cr = M.MODELOS["cranio_buti"]
    checar(u"no cranio_buti, o checkpoint dos arquivos tem o enxuto",
           set(cr["enxuto"]) == set(r for r, _t in cr["arquivos"]
                                    if r.endswith(".pth")))

    d = tempfile.mkdtemp(prefix="radai_teste_md5_")
    velho = os.environ.get("RADAI_MODELOS_DIR")
    sha = lambda b: hashlib.sha256(b).hexdigest()
    original, enxuto = b"o" * 10, b"e" * 4
    try:
        os.environ["RADAI_MODELOS_DIR"] = d
        M.MODELOS["fantoma_enx"] = {
            "nome": u"fantoma", "motor": "x", "embutido": False, "repo": "x/y",
            "url_direta": "file:///" + os.path.join(d, "nao_existe.bin")
            .replace("\\", "/"),
            "arquivos": [("ck.pth", 10)], "sha256": {"ck.pth": sha(original)},
            "enxuto": {"ck.pth": (4, sha(enxuto))},
            "licenca": u"x", "uso_permitido": "livre"}
        alvo = Path(d) / "fantoma_enx" / "ck.pth"
        alvo.parent.mkdir(parents=True)

        def baixou():
            try:
                return M.baixar("fantoma_enx").get("pulados"), u""
            except Exception as e:
                return None, u"%s: %s" % (type(e).__name__, e)
        alvo.write_bytes(enxuto)
        checar(u"o enxuto conta como instalado",
               M.estado_do_modelo("fantoma_enx")["instalado"],
               str(M.estado_do_modelo("fantoma_enx")))
        checar(u"  e o baixar o reconhece e não vai à origem",
               baixou()[0] == ["ck.pth"] and alvo.read_bytes() == enxuto,
               str(baixou()))
        alvo.write_bytes(b"x" * 4)
        checar(u"(isca) com o tamanho do enxuto e outro sha256, o baixar não "
               u"aceita e vai à origem", baixou()[0] is None, str(baixou()))
        alvo.write_bytes(b"x" * 7)
        checar(u"(isca) tamanho que não é nem o original nem o enxuto não "
               u"conta como instalado",
               not M.estado_do_modelo("fantoma_enx")["instalado"])
        alvo.write_bytes(original)
        checar(u"o original continua aceito",
               M.estado_do_modelo("fantoma_enx")["instalado"]
               and baixou()[0] == ["ck.pth"])

        cont = {"conteudo": [("a/ck.model", 10)],
                "sha256": {"a/ck.model": sha(original)},
                "enxuto": {"a/ck.model": (4, sha(enxuto))}}
        pasta = Path(d) / "fantoma_cont"
        (pasta / "a").mkdir(parents=True)

        def confere():
            try:
                M._conferir_conteudo(cont, pasta)
                return u""
            except Exception as e:
                return u"%s" % e
        (pasta / "a" / "ck.model").write_bytes(enxuto)
        checar(u"no conteúdo extraído (o formato do hnlnl), o enxuto não "
               u"falta", M._falta_do_conteudo(cont, pasta) == [])
        checar(u"  e confere pelo sha256 do enxuto", confere() == u"",
               confere())
        (pasta / "a" / "ck.model").write_bytes(b"x" * 4)
        checar(u"(isca) o enxuto com outro sha256 reprova",
               u"sha256" in confere(), confere())
    finally:
        M.MODELOS.pop("fantoma_enx", None)
        if velho is None:
            os.environ.pop("RADAI_MODELOS_DIR", None)
        else:
            os.environ["RADAI_MODELOS_DIR"] = velho
        shutil.rmtree(d, ignore_errors=True)


def teste_o_zip_ja_extraido_nao_baixa_de_novo():
    secao(u"o zip já extraído e conferido (a marca) não é baixado de novo "
          u"num preparo repetido")
    import zipfile
    import radai_models as M
    from pathlib import Path
    for ident in ("moose", "cads_open"):
        m = M.MODELOS[ident]
        checar(u"%s: todo arquivo baixado é um zip que se extrai" % ident,
               set(M.zips_a_extrair(m))
               == set(r for r, _t in m.get("arquivos") or ()),
               str(M.zips_a_extrair(m)))

    d = tempfile.mkdtemp(prefix="radai_teste_md5_")
    velho = os.environ.get("RADAI_MODELOS_DIR")
    morto = "file:///" + os.path.join(d, "nao_existe.zip").replace("\\", "/")
    try:
        os.environ["RADAI_MODELOS_DIR"] = d
        fonte2 = Path(d) / "origem_z2.zip"
        with zipfile.ZipFile(str(fonte2), "w") as z:
            z.writestr("b/ck.pth", b"b" * 32)
        n2 = fonte2.stat().st_size

        def fantoma(ident, **extra):
            m = {"nome": u"fantoma", "motor": "x", "embutido": False,
                 "repo": "x/y", "url_direta": morto,
                 "arquivos": [("z1.zip", 100)], "extrair": "z1.zip",
                 "licenca": u"x", "uso_permitido": "livre"}
            m.update(extra)
            M.MODELOS[ident] = m
            p = Path(d) / ident
            p.mkdir(parents=True, exist_ok=True)
            return p

        def baixou(ident):
            try:
                r = M.baixar(ident)
                return (r.get("baixados"), r.get("pulados")), u""
            except Exception as e:
                return None, u"%s: %s" % (type(e).__name__, e)

        p = fantoma("fantoma_zip")
        (p / "pesos_extraidos.txt").write_text(u"x", encoding="utf-8")
        r, erro = baixou("fantoma_zip")
        checar(u"com a marca da extração, o zip apagado não vai à origem",
               r == ([], ["z1.zip"]) and not (p / "z1.zip").exists(),
               str((r, erro)))
        (p / "pesos_extraidos.txt").unlink()
        r, erro = baixou("fantoma_zip")
        checar(u"(isca) sem a marca, o zip que falta vai à origem",
               r is None and erro, str((r, erro)))

        p = fantoma("fantoma_zip_cont", conteudo=[("a/ck.pth", 10)])
        (p / "pesos_extraidos.txt").write_text(u"x", encoding="utf-8")
        r, erro = baixou("fantoma_zip_cont")
        checar(u"(isca) com a marca e o conteúdo extraído faltando, o zip "
               u"vai à origem", r is None and erro, str((r, erro)))

        p = fantoma("fantoma_zip_dois",
                    arquivos=[("z1.zip", 100), ("z2.zip", n2)],
                    extrair=("z1.zip", "z2.zip"),
                    url_por_arquivo={"z2.zip": "file:///" + str(fonte2)
                                     .replace("\\", "/")})
        M._marca_do_zip(p, "z1.zip").write_text(u"x", encoding="utf-8")
        r, erro = baixou("fantoma_zip_dois")
        checar(u"com a marca de um zip só, ele fica e o outro é baixado e "
               u"extraído", r == (["z2.zip"], ["z1.zip"])
               and (p / "b" / "ck.pth").is_file()
               and (p / "pesos_extraidos.txt").is_file()
               and not (p / "z1.zip").exists(), str((r, erro)))
    finally:
        for ident in ("fantoma_zip", "fantoma_zip_cont", "fantoma_zip_dois"):
            M.MODELOS.pop(ident, None)
        if velho is None:
            os.environ.pop("RADAI_MODELOS_DIR", None)
        else:
            os.environ["RADAI_MODELOS_DIR"] = velho
        shutil.rmtree(d, ignore_errors=True)


def teste_os_em_breve_nao_baixam_nem_rodam():
    secao(u"TLI e os 19 órgãos ficam fora do pacote, e sem resto no código")
    import radai_models as M
    import radai_modes as MD
    import radai_motores_full as MF
    ids = ["hn_cubero", "tli_choi"]
    checar(u"o registro «em breve» saiu do código (sem tela, sem chamador)",
           not hasattr(M, "EM_BREVE") and not hasattr(M, "em_breve"))
    fonte = io.open(_componentes.fonte("app/radai_models.py"),
                    encoding="utf-8").read()
    checar(u"  e nenhum dos dois ids sobrou no radai_models",
           not any(i in fonte for i in ids))
    def _fora_do_pacote(modelos, catalogo):
        return not (set(ids) & set(modelos)) and not (set(ids) & set(catalogo))
    import json
    cat = [m["id"] for m in json.load(io.open(os.path.join(
        _componentes.raiz_da_suite(), "packager", "catalogo.json"), encoding="utf-8"))["modelos"]]
    checar(u"nenhum dos dois está no registro que o preparador baixa nem no "
           u"catálogo do pacote", _fora_do_pacote(M.MODELOS, cat),
           str(sorted(M.MODELOS)))
    checar(u"  (isca) um id «em breve» posto no registro reprova",
           not _fora_do_pacote(dict(M.MODELOS, tli_choi={}), cat))
    checar(u"  nem nos motores do FULL",
           set(MF.CODIGOS) == {"cranio_ct"}, str(MF.CODIGOS))
    checar(u"  nem nos motores dos modos",
           not {"hn19", "tli"} & set(MD.MOT_POR_COD), str(sorted(MD.MOT_POR_COD)))
    checar(u"  nem num protocolo",
           "linfonodal_tmli" not in MD.PROT_POR_COD)

    sem_motor = all(not os.path.exists(_componentes.fonte("app/" + n))
                    for n in ("radai_tli_engine.py", "radai_cubero_engine.py",
                              "radai_nnunet_v1.py"))
    checar(u"  e nenhum motor deles existe em app/", sem_motor)



def teste_peso_novo_muda_a_impressao_de_requisitos():
    secao(u"peso novo ou trocado muda a impressão de requisitos")
    sys.path.insert(0, os.path.join(_componentes.raiz_da_suite(), "build"))
    import requisitos as R
    d = tempfile.mkdtemp(prefix="radai_teste_req_")
    try:
        shutil.copytree(os.path.join(_componentes.raiz_da_suite(), "build"), os.path.join(d, "build"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        os.makedirs(os.path.join(d, "app"))
        for n in ("radai_tasks.py", "radai_models.py"):
            shutil.copy2(_componentes.fonte("app/" + n), os.path.join(d, "app", n))
        antes = R.calcular(d)[u"impressao"]
        checar(u"a impressão da cópia é a do repositório",
               antes == R.calcular(_componentes.raiz_da_suite())[u"impressao"])
        p = os.path.join(d, "app", "radai_models.py")
        t = io.open(p, encoding="utf-8").read()
        isca = t.replace("d098f10fd81292f2722cba5bed556ca411b4c6f778d3f12d00571bdf",
                         "0" * 56, 1)
        checar(u"  (a isca troca o sha256 do peso do encéfalo)", isca != t)
        io.open(p, "w", encoding="utf-8").write(isca)
        checar(u"o sha256 trocado MUDA a impressão",
               R.calcular(d)[u"impressao"] != antes)
        repo = R.calcular(RAIZ)
        trocado = R.calcular(d)
        _pode, mot = R.comparar(repo, trocado)
        checar(u"  e a recusa NOMEIA o modelo: «pesos trocados: cranio_buti»",
               u"pesos trocados: cranio_buti" in mot, mot)
        sem = dict(repo, modelos={k: v for k, v in repo[u"modelos"].items()
                                  if k != u"cranio_buti"}, impressao=u"x")
        _pode, mot = R.comparar(sem, repo)
        checar(u"  e o modelo que entrou: «modelo novo: cranio_buti»",
               u"modelo novo: cranio_buti" in mot, mot)
        v83 = {k: v for k, v in repo.items() if k != u"modelos"}
        v83[u"impressao"] = u"y"
        _pode, mot = R.comparar(v83, repo)
        checar(u"  a instalacao sem o bloco por modelo (v8.3) ouve quais o "
               u"pacote leva, e nao «a impressao difere»",
               any(u"cranio_buti" in m for m in mot)
               and not any(u"(a impressao difere)" in m for m in mot), mot)
        _pode, mot = R.comparar(dict(repo, impressao=u"z"), repo)
        checar(u"  (isca) sem diferenca nomeavel, continua o motivo generico",
               mot == [u"as bibliotecas ou os pesos mudaram (a impressao difere)"],
               mot)
        os.remove(p)
        try:
            R.calcular(d)
            levantou = False
        except ValueError:
            levantou = True
        checar(u"sem o registro de modelos a conta LEVANTA, e não compara "
               u"igual", levantou)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def teste_as_descricoes_sao_ascii_e_honestas():
    secao(u"a descrição de cada ROI nova é ASCII e diz de onde veio")
    import radai_cranio_engine as CR
    for k in CR.PARA_O_FULL.values():
        d = CR.descricao(k)
        checar(u"`%s`: ASCII e cita Buti" % k,
               all(ord(c) < 128 for c in d) and u"Buti" in d, d)
    checar(u"o quiasma diz o Dice do artigo e pede conferência",
           u"0,64" in CR.descricao("optic_chiasm")
           and u"confira" in CR.descricao("optic_chiasm"))


def teste_cranio_a_trava_dos_rotulos():
    secao(u"encéfalo em TC: a trava do mapa de rótulos")
    import radai_cranio_engine as CR
    checar(u"o mapa conferido passa",
           CR.conferir_rotulos(dict(CR.ROTULOS_CONFERIDOS)))
    trocado = dict(CR.ROTULOS_CONFERIDOS)
    trocado[5], trocado[6] = trocado[6], trocado[5]
    try:
        CR.conferir_rotulos(trocado)
        levantou = False
    except ValueError:
        levantou = True
    checar(u"  (isca) nervo esquerdo e direito trocados LEVANTAM", levantou)
    novo = dict(CR.ROTULOS_CONFERIDOS)
    novo[9] = "Tumor"
    try:
        CR.conferir_rotulos(novo)
        levantou = False
    except ValueError:
        levantou = True
    checar(u"  e rótulo novo cai fora por omissão", levantou)
    checar(u"a função que nomeia chama a trava",
           "conferir_rotulos(tabela)" in ler("app/radai_cranio_engine.py"))


def teste_cranio_o_que_vai_a_cada_arquivo():
    secao(u"encéfalo em TC: tronco e quiasma no OAR; o resto só no FULL")
    import radai_cranio_engine as CR
    import radai_sets as S
    rot = np.zeros((4, 4, 9), dtype=np.int8)
    for i in range(1, 9):
        rot[:, :, i] = i
    m = CR.masks_do_mapa(rot, dict(CR.ROTULOS_CONFERIDOS))
    checar(u"saem as cinco estruturas usadas",
           set(m) == set(CR.PARA_O_FULL.values()), str(sorted(m)))
    checar(u"  e não o encéfalo nem os nervos ópticos do modelo",
           not set(m) & {"brain", "optic_nerve_left", "optic_nerve_right"})
    checar(u"tronco e quiasma estão na lista do OAR",
           CR.NO_OAR <= S.PERMITIDOS_NO_OAR, str(sorted(CR.NO_OAR)))
    so_full = set(CR.PARA_O_FULL.values()) - set(CR.NO_OAR)
    checar(u"cerebelo, ventrículos e linha média NÃO estão na lista do OAR",
           not so_full & set(S.PERMITIDOS_NO_OAR), str(sorted(so_full)))
    import engine
    for k in CR.PARA_O_FULL.values():
        checar(u"`%s` tem nome TG-263 (ou forma nossa a conferir)" % k,
               k in engine.TG263)


def teste_cranio_o_tronco_dentro_do_encefalo_nao_e_alarme():
    secao(u"encéfalo em TC: o tronco dentro do encéfalo do TotalSegmentator")
    import engine
    import radai_geom
    g = radai_geom.Grade((2.0, 1.0, 1.0))
    enc = np.zeros((10, 20, 20), bool)
    enc[1:9, 2:18, 2:18] = True
    tronco = np.zeros_like(enc)
    tronco[2:7, 8:12, 8:12] = True
    pares = engine.sobreposicoes({"brain": enc, "brain_brainstem": tronco}, g,
                                 construcoes={}, estrito=True)
    checar(u"no OAR (modo estrito) o par encéfalo × tronco não é alarme",
           not pares, str(pares))
    pares = engine.sobreposicoes({"brain": enc, "liver": tronco}, g,
                                 construcoes={}, estrito=True)
    checar(u"  (isca) o mesmo volume com outro nome continua alarme",
           bool(pares), str(pares))


def teste_cranio_o_portao_e_o_recorte():
    secao(u"encéfalo em TC: o portão do encéfalo e o recorte")
    import radai_cranio_engine as CR
    g = _Grade((2.0, 1.0, 1.0))
    cru = {"brain": np.zeros((60, 80, 80), dtype=bool),
           "skull": np.zeros((60, 80, 80), dtype=bool)}
    cru["brain"][10:20, 20:40, 20:40] = True
    tem, motivo, v = CR.encefalo_no_campo(cru, g)
    checar(u"8 cm³ de encéfalo não abrem o portão", not tem, motivo)
    cru["brain"][10:50, 10:70, 10:70] = True
    tem, motivo, v = CR.encefalo_no_campo(cru, g)
    checar(u"288 cm³ abrem", tem, motivo)
    checar(u"sem a máscara do encéfalo, fechado",
           not CR.encefalo_no_campo({}, g)[0])
    z0, z1, y0, y1, x0, x1 = CR.caixa(cru, (60, 80, 80), g, margem_mm=10)
    checar(u"o recorte contém o encéfalo com a margem em mm",
           (z0, z1, y0, y1, x0, x1) == (5, 55, 0, 80, 0, 80),
           str((z0, z1, y0, y1, x0, x1)))


def teste_cranio_sem_espelhamento():
    secao(u"encéfalo em TC: inferência sem espelhamento, num filho")
    t = ler("app/radai_cranio_engine.py")
    checar(u"use_mirroring=False no script do filho",
           "use_mirroring=False" in t)
    checar(u"o filho tem o guarda de __main__",
           'if __name__ == "__main__":' in t and "freeze_support" in t)
    checar(u"stdout do filho vai para arquivo, e não para PIPE",
           "stdout=saida" in t and "PIPE" not in t)


def teste_alvo_nunca_no_oar():
    secao(u"a porta do FULL: alvo nunca vai ao OAR")
    import radai_motores_full as MF
    import radai_sets as S
    e = MF.Extras()
    e["alvos"]["ALVO01"] = np.zeros((2, 2, 2), bool)
    checar(u"alvo fora da lista do OAR passa",
           MF.conferir_destinos(e, S.PERMITIDOS_NO_OAR))
    try:
        MF.conferir_destinos(e, set(S.PERMITIDOS_NO_OAR) | {"ALVO01"})
        levantou = False
    except ValueError:
        levantou = True
    checar(u"  (isca) alvo na lista do OAR LEVANTA", levantou)
    t = ler("app/radai_output.py")
    checar(u"a porta chama a trava antes de juntar os alvos",
           "radai_motores_full.conferir_destinos(extras, permitidos)" in t)
    no_oar = MF.estruturas_no_oar()
    checar(u"o encéfalo leva o tronco e o quiasma ao OAR",
           set(no_oar) == {"cranio_ct"}
           and {"brain_brainstem", "optic_chiasm"} <= set(no_oar["cranio_ct"]),
           str(no_oar))


def teste_os_orgaos_entram_sem_copiar_as_cruas():
    secao(u"a porta do FULL: os órgãos entram na sobreposição, sem cópia")
    import radai_output as RO

    class Pregui(object):
        def __init__(self):
            self.d = {"liver": 1}
            self.lidas = 0

        def __contains__(self, k):
            return k in self.d

        def __setitem__(self, k, v):
            self.d[k] = v

        def __iter__(self):
            return iter(self.d)

        def keys(self):
            return list(self.d)

        def __getitem__(self, k):
            self.lidas += 1
            return self.d[k]

    p = Pregui()
    ex = {"orgaos": {"optic_chiasm": 2, "liver": 9},
          "origem": {"optic_chiasm": "cranio_ct", "liver": "x"}}
    m, o = RO._juntar_orgaos_dos_motores(p, {"liver": "ts"}, ex)
    checar(u"a sobreposição é a mesma (não virou dict)", m is p)
    checar(u"nenhuma máscara foi lida", p.lidas == 0, str(p.lidas))
    checar(u"o quiasma entrou com a origem do motor",
           p.d.get("optic_chiasm") == 2 and o["optic_chiasm"] == "cranio_ct")
    checar(u"a fonte do TotalSegmentator ganha no nome repetido",
           p.d["liver"] == 1 and o["liver"] == "ts")


def teste_tempo_de_cada_etapa_no_log():
    secao(u"o tempo de cada etapa e a soma vão ao log")
    import radai_motores_full as MF
    linhas = []
    MF.dizer_tempos(u"motor cranio_ct", [(u"recorte", 1.0), (u"inferencia", 2.5)],
                    linhas.append)
    checar(u"uma linha com cada etapa e a soma",
           linhas and u"recorte 1.0 s" in linhas[0]
           and u"inferencia 2.5 s" in linhas[0]
           and u"soma 3.5 s" in linhas[0], str(linhas))
    for mod in ("radai_cranio_engine",):
        t = ler("app/%s.py" % mod)
        checar(u"`%s` mede recorte, inferência e volta" % mod,
               t.count("_marca(") >= 3)


def teste_na_rm_nenhum_roda():
    secao(u"o motor do FULL é de TC")
    import radai_motores_full as MF
    linhas = []
    e = MF.motores_na_serie(None, {}, list(MF.CODIGOS), log=linhas.append,
                          modalidade="MR")
    checar(u"na RM devolve vazio e diz por quê",
           e.vazio() and any(u"de TC" in l for l in linhas), str(linhas))


def _serie_com_encefalo(grande=True):
    import SimpleITK as sitk
    ref = sitk.Image(80, 80, 60, sitk.sitkInt16)
    ref.SetSpacing((1.0, 1.0, 2.0))
    brain = np.zeros((60, 80, 80), dtype=bool)
    if grande:
        brain[10:50, 10:70, 10:70] = True
    else:
        brain[10:20, 20:40, 20:40] = True
    skull = np.zeros_like(brain)
    return ref, {"total_v3": {"brain": brain, "skull": skull}}


def _rodar_o_motor(MF, CR, peso=True, grande=True, rodar_falha=None,
                   modalidade="CT"):
    velho_d, velho_r = CR.disponivel, CR.rodar
    CR.disponivel = (lambda base=None: (True, u"pasta")) if peso else (
        lambda base=None: (False, u"os pesos do modelo do cranio nao estao "
                                  u"nesta instalacao"))
    if rodar_falha:
        CR.rodar = lambda *a, **k: (False, rodar_falha)
    linhas = []
    try:
        ref, cruas = _serie_com_encefalo(grande)
        e = MF.motores_na_serie(ref, cruas, [MF.COD_CRANIO],
                                log=linhas.append, modalidade=modalidade)
    finally:
        CR.disponivel, CR.rodar = velho_d, velho_r
    return e, linhas


def _faltou_do_motor(MF, extras):
    import radai_records as RG
    return RG.faltou_da_serie(
        (), (), motores_falharam=(extras or {}).get("falhas"),
        estruturas_do_motor=MF.estruturas_do_motor)


def _o_motor_que_falha_entra_no_faltou(MF):
    import radai_cranio_engine as CR
    e, _l = _rodar_o_motor(MF, CR, peso=False)
    nomes = [x["estrutura"] for x in _faltou_do_motor(MF, e)]
    return {"brain_brainstem", "optic_chiasm"} <= set(nomes)


def teste_o_motor_sem_peso_ou_com_falha_entra_no_faltou():
    secao(u"o encéfalo sem peso ou com falha entra no que faltou")
    import radai_motores_full as MF
    import radai_cranio_engine as CR
    e, linhas = _rodar_o_motor(MF, CR, peso=False)
    falhas = list(e.get("falhas") or ())
    checar(u"sem peso, com encéfalo no campo: o motor vai às falhas "
           u"(sem_peso), sem derrubar a série",
           [(f.get("motor"), f.get("classe")) for f in falhas]
           == [(MF.COD_CRANIO, u"sem_peso")] and e.vazio(), str(falhas))
    f = _faltou_do_motor(MF, e)
    nomes = [x["estrutura"] for x in f]
    checar(u"  e o faltou lista o tronco e o quiasma (as do OAR) e as do "
           u"FULL, com o porquê",
           {"brain_brainstem", "optic_chiasm"} <= set(nomes)
           and set(MF.estruturas_no_full()[MF.COD_CRANIO]) <= set(nomes)
           and all(x["porque"].startswith(u"cranio_ct: sem_peso") for x in f),
           str(f))
    checar(u"  e as do OAR vêm primeiro", nomes[:2] == sorted(
        MF.estruturas_no_oar()[MF.COD_CRANIO]), str(nomes))
    e, linhas = _rodar_o_motor(MF, CR, peso=False, grande=False)
    checar(u"sem peso e SEM encéfalo no campo: não se aplica, silencioso",
           not e.get("falhas") and not _faltou_do_motor(MF, e),
           str(e.get("falhas")))
    e, linhas = _rodar_o_motor(MF, CR, peso=False, modalidade="MR")
    checar(u"sem peso na RM: não se aplica, silencioso",
           not e.get("falhas"), str(e.get("falhas")))
    e, linhas = _rodar_o_motor(MF, CR, peso=True,
                               rodar_falha=u"o processo saiu com codigo 1")
    falhas = list(e.get("falhas") or ())
    checar(u"o motor que levanta vai às falhas (falhou), e a série segue",
           [(x.get("motor"), x.get("classe")) for x in falhas]
           == [(MF.COD_CRANIO, u"falhou")]
           and u"codigo 1" in (falhas[0].get("motivo") or u""), str(falhas))
    checar(u"  e entra no faltou",
           u"brain_brainstem" in [x["estrutura"]
                                  for x in _faltou_do_motor(MF, e)])
    e = MF.falha_de_todos([MF.COD_CRANIO], u"falhou", u"ImportError: x")
    checar(u"a falha antes do motor (a porta) também vai às falhas",
           [x.get("motor") for x in e.get("falhas") or ()] == [MF.COD_CRANIO]
           and u"brain_brainstem" in [x["estrutura"]
                                      for x in _faltou_do_motor(MF, e)])
    checar(u"o motor que funcionou passa calado",
           _faltou_do_motor(MF, MF.Extras()) == [])

    fonte = ler("app/radai_motores_full.py")
    alvo = u'fora["falhas"].append('
    isca = fonte.replace(alvo, u"(lambda _x: None)(")
    checar(u"a isca acha o registro da falha no motor", isca != fonte)
    mod = types.ModuleType("radai_motores_full_isca")
    exec(compile(isca, "<isca-so-loga>", "exec"), mod.__dict__)
    checar(u"ISCA: o motor que só loga não põe nada no faltou -- a checagem "
           u"reprova", _o_motor_que_falha_entra_no_faltou(MF)
           and not _o_motor_que_falha_entra_no_faltou(mod))


def _porta_passa_as_falhas(fonte, nome_dos_extras):
    import ast
    for no in ast.walk(ast.parse(fonte)):
        if isinstance(no, ast.Call) and getattr(
                no.func, "attr", getattr(no.func, "id", "")) \
                == "faltou_da_serie":
            kw = {k.arg: k.value for k in no.keywords}
            v = kw.get("motores_falharam")
            if v is None or "estruturas_do_motor" not in kw:
                return False
            return nome_dos_extras in ast.dump(v)
    return False


def teste_as_duas_portas_passam_as_falhas_do_motor():
    secao(u"as duas portas passam as falhas do motor ao faltou")
    for rel, nome in (("app/radai_watcher.py", "_extras_da_vez"),
                      ("app/radai_batch.py", "extras_da_vez")):
        fonte = ler(rel)
        checar(u"`%s` passa `motores_falharam` dos extras e "
               u"`estruturas_do_motor` ao `faltou_da_serie`" % rel,
               _porta_passa_as_falhas(fonte, nome))
        isca = fonte.replace(u"motores_falharam=", u"_motores_ignorados=")
        checar(u"  isca: sem `motores_falharam` reprova",
               isca != fonte and not _porta_passa_as_falhas(isca, nome))
    for rel in ("app/radai_watcher.py", "app/radai_batch.py"):
        checar(u"`%s`: a exceção antes do motor vira falha registrada "
               u"(`falha_de_todos`)" % rel, u"falha_de_todos(" in ler(rel))


def teste_modos_e_protocolos():
    secao(u"onde cada um roda")
    import radai_modes as MD
    import radai_batch as B
    checar(u"o AUTO pede o encéfalo no crânio e na cabeça e pescoço",
           MD.motores_do_auto([MD.CRANIO]) == ("cranio_ct",)
           and MD.motores_do_auto([MD.CABECA_PESCOCO]) == ("cranio_ct",))
    checar(u"  e não no tórax", MD.motores_do_auto([MD.TORAX]) == ())
    checar(u"  nem na RM",
           MD.motores_do_auto([MD.CRANIO], modalidade="MR") == ())
    checar(u"o protocolo Crânio liga o encéfalo",
           "cranio_ct" in MD.PROT_POR_COD["cranio"]["motores"])
    cp = MD.PROT_POR_COD["cabeca_pescoco"]["motores"]
    checar(u"o Cabeça e Pescoço avançado liga os níveis e o encéfalo",
           tuple(cp) == ("hnlnl", "cranio_ct"), str(cp))
    MD.conferir_protocolos()
    checar(u"a tabela de protocolos passa na trava", True)
    esc = {"modo": "perso", "modalidade": "CT", "protocolos": (),
           "tasks": {}, "comparacao": {}}
    m = B.motores_do_perso(esc)
    checar(u"no PERSONALIZADO sem protocolo, o encéfalo nasce em 0",
           not m["cranio_ct"], str(m))
    checar(u"  e não há chave dos modelos «em breve»",
           "hn19" not in m and "tli" not in m, str(sorted(m)))
    m = B.motores_do_perso(dict(esc, protocolos=("cranio",)))
    checar(u"o protocolo Crânio liga o encéfalo", m["cranio_ct"])
    m = B.motores_do_perso(dict(esc, protocolos=("cabeca_pescoco",),
                                tasks={"cranio_ct": 0}))
    checar(u"a chave em 0 vence o protocolo", not m["cranio_ct"])
    m = B.motores_do_perso(dict(esc, modalidade="MR", tasks={"cranio_ct": 1}))
    checar(u"  e na RM nunca", not m["cranio_ct"])
    checar(u"a chave de motor não vira task do TotalSegmentator",
           "cranio_ct" not in B._chaves_de_task(
               {"tasks": {"cranio_ct": 1, "teeth": 1}}))


def teste_a_tela_mostra_o_encefalo():
    secao(u"a coluna das tasks do PERSONALIZADO mostra o encéfalo (só TC)")
    import radai_batch as B
    itens = B._itens_dos_motores_do_full("CT")
    checar(u"um item de motor", [i["task"] for i in itens] == ["cranio_ct"],
           str([i["task"] for i in itens]))
    checar(u"cada um diz o arquivo (FULL) e o aviso",
           all(i["arquivo"] == u"FULL" and i["avisos"] for i in itens))
    checar(u"na RM, nenhum", B._itens_dos_motores_do_full("MR") == [])


def teste_a_previa_diz_tronco_e_quiasma():
    secao(u"a prévia da entrega diz tronco e quiasma, com a condição")
    import radai_batch as B
    p = B.previa_da_entrega({"modo": "perso", "modalidade": "CT",
                             "protocolos": ["cranio"]})
    ks = dict((x["chave"], x) for x in p["oar"]["estruturas"])
    checar(u"o protocolo Crânio põe tronco e quiasma na prévia do OAR",
           "brain_brainstem" in ks and "optic_chiasm" in ks, str(sorted(ks)))
    checar(u"  com a condição do encéfalo no campo",
           ks.get("optic_chiasm", {}).get("condicao")
           == B.CONDICAO_DO_ENCEFALO_NA_PREVIA)
    p2 = B.previa_da_entrega({"modo": "perso", "modalidade": "CT",
                              "protocolos": ["torax_mama"]})
    checar(u"  (isca) sem o encéfalo pedido, não aparecem",
           "optic_chiasm" not in [x["chave"] for x in p2["oar"]["estruturas"]])
    p3 = B.previa_da_entrega({"modo": "fast", "modalidade": "CT"})
    checar(u"  e no FAST, nunca",
           "optic_chiasm" not in [x["chave"] for x in p3["oar"]["estruturas"]])
    p4 = B.previa_da_entrega({"modo": "auto", "modalidade": "CT"})
    checar(u"  no AUTO de TC aparecem, condicionados",
           "optic_chiasm" in [x["chave"] for x in p4["oar"]["estruturas"]])


def teste_o_quiasma_e_suavizado_como_o_nervo_optico():
    secao(u"o quiasma do modelo do encéfalo é estrutura delgada, como o "
          u"nervo óptico")
    import engine as E

    def _como_o_nervo():
        q = E.suavizacao_de("optic_chiasm")
        n = E.suavizacao_de("optic_nerve_left")
        return q, n, (q == n and q < E.SUAVIZACAO_PADRAO_MM)
    q, n, ok = _como_o_nervo()
    checar(u"o quiasma não cai no padrão por omissão",
           ok, u"quiasma %.2f mm, nervo %.2f mm, padrão %.2f mm"
           % (q, n, E.SUAVIZACAO_PADRAO_MM))
    checar(u"  e está nas estruturas delgadas: sem suavização da máscara e "
           u"poupado da redução de pontos",
           "optic_chiasm" in E.ESTRUTURAS_DELGADAS and q == 0.0,
           str(E.ESTRUTURAS_DELGADAS))
    velho = E.SUAVIZACAO.get("optic_chiasm")
    try:
        E.SUAVIZACAO["optic_chiasm"] = E.SUAVIZACAO["eye_lens_left"]
        qi, _ni, ok_i = _como_o_nervo()
    finally:
        E.SUAVIZACAO["optic_chiasm"] = velho
    checar(u"ISCA: com o quiasma na lista das pequenas (a suavização de "
           u"antes), a checagem de cima reprova", not ok_i,
           u"quiasma %.2f mm" % qi)


def _vigia_passa_os_extras(fonte):
    import ast
    arvore = ast.parse(fonte)
    for fn in ast.walk(arvore):
        if not isinstance(fn, ast.FunctionDef):
            continue
        dos_motores = set()
        for no in ast.walk(fn):
            if (isinstance(no, ast.Assign) and isinstance(no.value, ast.Call)
                    and getattr(no.value.func, "id", "") ==
                    "_rodar_motores_do_full"):
                dos_motores |= set(t.id for t in no.targets
                                   if isinstance(t, ast.Name))
        if not dos_motores:
            continue
        for no in ast.walk(fn):
            if (isinstance(no, ast.Call)
                    and getattr(no.func, "attr", "") == "full_e_oar"):
                for kw in no.keywords:
                    if (kw.arg == "extras" and isinstance(kw.value, ast.Name)
                            and kw.value.id in dos_motores):
                        return True
    return False


def teste_o_vigia_passa_os_motores_ao_full():
    secao(u"o vigia roda os motores do FULL e entrega o que eles devolvem")
    fonte = ler("app/radai_watcher.py")
    checar(u"o `full_e_oar` do vigia recebe o que `_rodar_motores_do_full` "
           u"devolveu", _vigia_passa_os_extras(fonte))
    isca = fonte.replace("modo=MODO_DO_VIGIA, extras=_extras_da_vez)",
                         "modo=MODO_DO_VIGIA)")
    checar(u"isca: sem `extras=` a checagem reprova",
           isca != fonte and not _vigia_passa_os_extras(isca))
    import radai_modes
    checar(u"o AUTO de TC com o crânio pede o motor do encéfalo",
           bool(radai_modes.motores_do_auto(("cranio",), "CT")),
           str(radai_modes.motores_do_auto(("cranio",), "CT")))


def _narrativa_em_comentario(fonte):
    import ast
    import re
    import tokenize
    padrao = re.compile(r"\bv\d+\.\d+\b|\d{2}/\d{2}/\d{4}|\bet al\.")
    textos = [t.string for t in tokenize.generate_tokens(
        io.StringIO(fonte).readline) if t.type == tokenize.COMMENT]
    for no in ast.walk(ast.parse(fonte)):
        if isinstance(no, (ast.Module, ast.FunctionDef, ast.ClassDef)):
            d = ast.get_docstring(no)
            if d:
                textos.append(d)
    return [t.strip()[:80] for t in textos if padrao.search(t)]


def teste_os_modulos_novos_sem_narrativa():
    secao(u"os módulos novos não narram versão, data nem citação")
    for rel in ("app/radai_cranio_engine.py", "app/radai_motores_full.py"):
        achou = _narrativa_em_comentario(ler(rel))
        checar(u"`%s` sem versão, data nem citação em comentário" % rel,
               not achou, u" | ".join(achou))
    checar(u"isca: um comentário com versão reprova",
           bool(_narrativa_em_comentario(u"x = 1  # entrou na v8.4\n")))


def _secao_do_cranio_no_notice(notice):
    i = notice.find(u"CT Brain Segmentation Radiotherapy")
    if i < 0:
        return u""
    j = notice.find(u"-" * 40, i + 200)
    return notice[i:j if j > 0 else None]


def _mit_reproduzida(secao):
    t = u" ".join(secao.split())
    return (u"Permission is hereby granted, free of charge" in t
            and u"The above copyright notice and this permission notice "
                u"shall be included in all copies" in t
            and u'THE SOFTWARE IS PROVIDED "AS IS"' in t)


def teste_a_mit_do_cranio_vai_por_extenso():
    secao(u"a MIT dos pesos do encéfalo vai por extenso no NOTICE")
    sec = _secao_do_cranio_no_notice(ler("NOTICE"))
    checar(u"a seção do modelo existe no NOTICE", bool(sec))
    checar(u"a permissão e a isenção da MIT estão na seção do modelo",
           _mit_reproduzida(sec))
    checar(u"a seção diz que a origem não publica linha de copyright",
           u"copyright" in sec.lower() and u"Hugging Face" in sec)
    checar(u"isca: só o link SPDX reprova",
           not _mit_reproduzida(u"Licenca MIT https://spdx.org/licenses/MIT"))


def main():
    print("=" * 70)
    print(u"  o modelo do encéfalo no FULL e os modelos «em breve»")
    print("=" * 70)
    for t in (teste_o_registro_tem_o_do_cranio,
              teste_a_url_do_hugging_face_e_fixa,
              teste_o_md5_reprova_o_arquivo_trocado,
              teste_o_registro_aceita_o_par_original_e_enxuto,
              teste_o_zip_ja_extraido_nao_baixa_de_novo,
              teste_os_em_breve_nao_baixam_nem_rodam,
              teste_peso_novo_muda_a_impressao_de_requisitos,
              teste_as_descricoes_sao_ascii_e_honestas,
              teste_cranio_a_trava_dos_rotulos,
              teste_cranio_o_que_vai_a_cada_arquivo,
              teste_cranio_o_portao_e_o_recorte,
              teste_cranio_o_tronco_dentro_do_encefalo_nao_e_alarme,
              teste_cranio_sem_espelhamento,
              teste_alvo_nunca_no_oar,
              teste_os_orgaos_entram_sem_copiar_as_cruas,
              teste_tempo_de_cada_etapa_no_log,
              teste_na_rm_nenhum_roda,
              teste_o_motor_sem_peso_ou_com_falha_entra_no_faltou,
              teste_as_duas_portas_passam_as_falhas_do_motor,
              teste_modos_e_protocolos,
              teste_a_tela_mostra_o_encefalo,
              teste_a_previa_diz_tronco_e_quiasma,
              teste_o_quiasma_e_suavizado_como_o_nervo_optico,
              teste_o_vigia_passa_os_motores_ao_full,
              teste_os_modulos_novos_sem_narrativa,
              teste_a_mit_do_cranio_vai_por_extenso):
        try:
            t()
        except Exception as e:
            import traceback
            checar(u"%s (excecao)" % t.__name__, False,
                   "%s: %s" % (type(e).__name__, e))
            traceback.print_exc()
    falhas = [(n, d) for n, ok, d in _R if not ok]
    print("\n" + "=" * 70)
    if falhas:
        print(u"FALHOU: %d de %d checagens" % (len(falhas), len(_R)))
        for n, d in falhas:
            print(u"  - %s%s" % (n, ("  [%s]" % d) if d else ""))
    else:
        print(u"OK: %d checagens, todas passaram" % len(_R))
    print("=" * 70)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
