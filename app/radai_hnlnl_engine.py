# -*- coding: utf-8 -*-
import json
import os
import pickle
import re
import sys


VERSAO = "1.0"
IDENT = "hnlnl"

TAREFA = "Task110_HNLNFixed_MirrorBest"
TREINADOR = "nnUNetTrainerV2__nnUNetPlansv2.1"
PASTA_DO_ENSEMBLE = ("ensemble_3d_fullres__nnUNetTrainerV2__nnUNetPlansv2.1"
                     "--2d__nnUNetTrainerV2__nnUNetPlansv2.1")
FOLDS = (0, 1, 2, 3, 4)
REDE_DO_ENSEMBLE = u"ensemble 2D+3D (10 pesos)"

_CONV = re.compile(r"^(?P<raiz>conv_blocks_(?:context|localization))\."
                   r"(?P<caminho>[\d.]+?)blocks\.(?P<b>\d+)\.conv\.weight$")


INDICES_PERMITIDOS = frozenset(range(0, 21))

TETO_DE_CLASSES = 21


def conferir_niveis(indices):
    fora = sorted(set(int(i) for i in (indices or []))
                  - set(INDICES_PERMITIDOS))
    if fora:
        raise ValueError(
            u"PAREI: %d classe(s) fora dos 20 níveis linfonodais: %s.\n\n"
            u"Esta lista guarda o ESPAÇO DE SAÍDA DESTE MOTOR (20 níveis mais "
            u"o fundo), e não o que o aplicativo tem permissão de fazer. "
            u"Classe que ele nunca entregou aparecendo aqui quer dizer, quase "
            u"sempre, que o ARQUIVO DE PESOS é outro — e peso trocado entra "
            u"calado: a rede monta, o contorno sai plausível, e o nome que "
            u"chega ao RTSTRUCT é o do nível errado.\n\n"
            u"Detecção não é proibida neste aplicativo: ela é ATO DECLARADO "
            u"de quem opera, escolhida pelo nome da task, num modo que diz no "
            u"rótulo o que faz. Rótulo que aparece sozinho dentro de um "
            u"arquivo de pesos não foi escolhido por ninguém. E o que ele "
            u"nomeia importa, porque é pelo que entrega que a RDC 751/2022 "
            u"classifica o dispositivo: 'nível comprometido' entrega "
            u"conclusão, e não compartimento.\n\n"
            u"Se o modelo mudou, quem decide o que entra é gente."
            % (len(fora), ", ".join(str(x) for x in fora[:8])))
    return True


def pasta_dos_pesos(raiz_modelos=None, rede="3d_fullres"):
    if raiz_modelos is None:
        try:
            import radai_models
            raiz_modelos = str(radai_models.pasta_do_modelo(IDENT))
        except Exception:
            return ""
    base = os.path.join(str(raiz_modelos), rede, TAREFA, TREINADOR)
    return base if os.path.isfile(os.path.join(base, "plans.pkl")) else ""


def plano(base):
    with open(os.path.join(base, "plans.pkl"), "rb") as f:
        p = pickle.load(f)
    est = p["plans_per_stage"][sorted(p["plans_per_stage"])[-1]]
    ip = (p["dataset_properties"].get("intensityproperties") or {}).get(0) or {}
    return {
        "patch": tuple(int(x) for x in est["patch_size"]),
        "spacing": tuple(float(x) for x in est["current_spacing"]),
        "pool": [list(map(int, x)) for x in est["pool_op_kernel_sizes"]],
        "classes_primeiro_plano": int(p["num_classes"]),
        "clip": (float(ip.get("percentile_00_5", -1024.0)),
                 float(ip.get("percentile_99_5", 3071.0))),
        "media": float(ip.get("mean", 0.0)),
        "desvio": float(ip.get("sd", 1.0)) or 1.0,
    }




def _classes(torch, dim=3):
    import torch.nn as nn
    Conv = nn.Conv3d if dim == 3 else nn.Conv2d
    Norm = nn.InstanceNorm3d if dim == 3 else nn.InstanceNorm2d
    ConvT = nn.ConvTranspose3d if dim == 3 else nn.ConvTranspose2d

    class Bloco(nn.Module):

        def __init__(self, ci, co, k, s):
            super(Bloco, self).__init__()
            pad = tuple((int(x) - 1) // 2 for x in k)
            self.conv = Conv(ci, co, tuple(int(x) for x in k),
                             tuple(int(x) for x in s), pad, bias=True)
            self.instnorm = Norm(co, affine=True, eps=1e-5)
            self.lrelu = nn.LeakyReLU(negative_slope=1e-2, inplace=True)

        def forward(self, x):
            return self.lrelu(self.instnorm(self.conv(x)))

    class Pilha(nn.Module):

        def __init__(self, blocos):
            super(Pilha, self).__init__()
            self.blocks = nn.Sequential(*blocos)

        def forward(self, x):
            return self.blocks(x)

    class GenericUNetV1(nn.Module):
        def __init__(self, sd, pool):
            super(GenericUNetV1, self).__init__()
            ctx, loc = _mapa(sd, "conv_blocks_context"), _mapa(
                sd, "conv_blocks_localization")
            n_up = len(pool)

            estagios = []
            for e in sorted(ctx):
                p = _pilhas(Bloco, Pilha, ctx[e], pool[e - 1] if e else None)
                estagios.append(nn.Sequential(*p) if len(p) > 1 else p[0])
            self.conv_blocks_context = nn.ModuleList(estagios)

            self.tu = nn.ModuleList([
                ConvT(
                    int(sd["tu.%d.weight" % u].shape[0]),
                    int(sd["tu.%d.weight" % u].shape[1]),
                    tuple(int(x) for x in sd["tu.%d.weight" % u].shape[2:]),
                    tuple(int(x) for x in sd["tu.%d.weight" % u].shape[2:]),
                    bias=False)
                for u in range(n_up)])

            self.conv_blocks_localization = nn.ModuleList([
                nn.Sequential(*_pilhas(Bloco, Pilha, loc[u], None))
                for u in sorted(loc)])

            self.seg_outputs = nn.ModuleList([
                Conv(int(sd["seg_outputs.%d.weight" % u].shape[1]),
                          int(sd["seg_outputs.%d.weight" % u].shape[0]),
                          1, bias=False)
                for u in range(n_up)])

        def forward(self, x):
            skips = []
            for d in range(len(self.conv_blocks_context) - 1):
                x = self.conv_blocks_context[d](x)
                skips.append(x)
            x = self.conv_blocks_context[-1](x)
            saida = None
            for u in range(len(self.tu)):
                x = self.tu[u](x)
                x = torch.cat((x, skips[-(u + 1)]), dim=1)
                x = self.conv_blocks_localization[u](x)
                saida = self.seg_outputs[u](x)
            return saida

    return GenericUNetV1


def _mapa(sd, raiz):
    import collections
    d = collections.defaultdict(lambda: collections.defaultdict(list))
    for k in sd:
        m = _CONV.match(k)
        if not m or m.group("raiz") != raiz:
            continue
        partes = [int(x) for x in m.group("caminho").split(".") if x != ""]
        d[partes[0]][tuple(partes[1:])].append(
            (int(m.group("b")), tuple(sd[k].shape)))
    for e in d:
        for s in d[e]:
            d[e][s].sort()
    return d


def _pilhas(Bloco, Pilha, mapa_est, stride_do_primeiro):
    saida, ja = [], False
    for sub in sorted(mapa_est):
        blocos = []
        for _b, forma in mapa_est[sub]:
            co, ci = int(forma[0]), int(forma[1])
            k = tuple(int(x) for x in forma[2:])
            s = (1,) * len(k)
            if not ja and stride_do_primeiro is not None:
                s = tuple(int(x) for x in stride_do_primeiro)
            ja = True
            blocos.append(Bloco(ci, co, k, s))
        saida.append(Pilha(blocos))
    return saida


def _torch_device(d):
    d = str(d or "").strip().lower()
    if d in ("gpu", "cuda"):
        return "cuda"
    if d.startswith("cuda:"):
        return d
    return "cpu"


_SINAIS_DE_PLACA = (
    "out of memory",
    "outofmemoryerror",
    "cuda",
    "cudnn",
    "cublas",
    "nvidia",
)


def erro_de_placa(exc):
    texto = (u"%s: %s" % (type(exc).__name__, exc)).strip()
    if any(s in texto.lower() for s in _SINAIS_DE_PLACA):
        return texto.splitlines()[0][:160]
    return None


def carregar(base, fold=0, device="cpu"):
    import torch
    device = _torch_device(device)
    p = plano(base)
    alvo = os.path.join(base, "fold_%d" % fold, "model_final_checkpoint.model")
    if not os.path.isfile(alvo):
        raise IOError("nao achei os pesos do fold %d em %s" % (fold, base))
    ck = torch.load(alvo, map_location="cpu", weights_only=False)
    sd = ck["state_dict"]
    if int(sd["seg_outputs.0.weight"].shape[0]) != TETO_DE_CLASSES:
        raise ValueError(
            "os pesos entregam %d classes, e este motor conhece %d (20 niveis "
            "mais o fundo). Modelo trocado: quem decide o que entra e gente."
            % (int(sd["seg_outputs.0.weight"].shape[0]), TETO_DE_CLASSES))
    dim = int(sd["seg_outputs.0.weight"].dim()) - 2
    rede = _classes(torch, dim)(sd, p["pool"])
    rede.load_state_dict(sd, strict=True)
    p["canais"] = int(sd["seg_outputs.0.weight"].shape[0])
    rede.eval()
    rede.to(device)
    return rede, p




def _gauss(patch, np):
    from scipy import ndimage
    centro = np.zeros(patch, dtype=np.float32)
    centro[tuple(s // 2 for s in patch)] = 1.0
    g = ndimage.gaussian_filter(centro, [s / 8.0 for s in patch], mode="constant")
    g = g / g.max()
    g[g < 0.1] = 0.1
    return g


def _passos(n, patch, sobreposicao=0.5):
    if n <= patch:
        return [0]
    passo = max(1, int(round(patch * (1.0 - sobreposicao))))
    ps = list(range(0, n - patch + 1, passo))
    if ps[-1] != n - patch:
        ps.append(n - patch)
    return ps


def inferir(rede, vol, p, device="cpu", log=None, probabilidades=False):
    import numpy as np
    import torch

    device = _torch_device(device)
    patch = tuple(p["patch"])
    dois_d = len(patch) == 2
    janela = ((1,) + patch) if dois_d else patch
    orig = vol.shape
    pad = [max(0, janela[i] - vol.shape[i]) for i in range(3)]
    if any(pad):
        vol = np.pad(vol, [(0, pad[i]) for i in range(3)], mode="constant",
                     constant_values=float(vol.min()))
    g = _gauss(patch, np)
    if dois_d:
        g = g[None]
    canais = int(p.get("canais") or 0)
    if canais <= 0:
        raise ValueError("o plano nao traz `canais`: chame `carregar` primeiro")
    acum = np.zeros((canais,) + vol.shape, dtype=np.float32)
    peso = np.zeros(vol.shape, dtype=np.float32)
    if dois_d:
        zs = list(range(vol.shape[0]))
        ys, xs = (_passos(vol.shape[i], janela[i]) for i in (1, 2))
    else:
        zs, ys, xs = (_passos(vol.shape[i], patch[i]) for i in range(3))
    total = len(zs) * len(ys) * len(xs)
    feito = 0
    with torch.no_grad():
        for z in zs:
            for y in ys:
                for x in xs:
                    rec = (slice(z, z + janela[0]), slice(y, y + janela[1]),
                           slice(x, x + janela[2]))
                    bloco = vol[rec].astype("float32")
                    t = torch.from_numpy(
                        (bloco[0] if dois_d else bloco)[None, None]).to(device)
                    saida = torch.softmax(rede(t), dim=1)[0].cpu().numpy()
                    if dois_d:
                        saida = saida[:, None]
                    acum[(slice(None),) + rec] += saida * g
                    peso[rec] += g
                    feito += 1
                    if log and feito % 10 == 0:
                        log("  janela %d/%d" % (feito, total))
    peso[peso == 0] = 1.0
    if probabilidades:
        acum /= peso[None]
        return acum[:, :orig[0], :orig[1], :orig[2]]
    rot = np.argmax(acum, axis=0).astype("int8")
    del acum
    return rot[:orig[0], :orig[1], :orig[2]]


def pastas_do_ensemble(base3d):
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(str(base3d))))
    return str(base3d), os.path.join(raiz, "2d", TAREFA, TREINADOR)


def arquivos_do_ensemble():
    fora = []
    for rede in ("3d_fullres", "2d"):
        raiz = "%s/%s/%s" % (rede, TAREFA, TREINADOR)
        fora.append(raiz + "/plans.pkl")
        fora.extend("%s/fold_%d/model_final_checkpoint.model" % (raiz, f)
                    for f in FOLDS)
    fora.append("ensembles/%s/%s/postprocessing.json"
                % (TAREFA, PASTA_DO_ENSEMBLE))
    return fora


def faltam_do_ensemble(base3d):
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(str(base3d))))
    return [r for r in arquivos_do_ensemble()
            if not os.path.isfile(os.path.join(raiz, *r.split("/")))]


def inferir_ensemble(base3d, vol, device="cpu", log=None):
    import numpy as np
    b3, b2 = pastas_do_ensemble(base3d)
    if tuple(plano(b3)["spacing"]) != tuple(plano(b2)["spacing"]):
        raise ValueError("o 2D e o 3D nao tem o mesmo espacamento de trabalho")
    soma = None
    for nome, base in (("3d", b3), ("2d", b2)):
        for f in FOLDS:
            if log:
                log("  %s fold %d" % (nome, f))
            rede, p = carregar(base, fold=f, device=device)
            pr = inferir(rede, vol, p, device=device, log=log,
                         probabilidades=True)
            del rede
            if soma is None:
                soma = pr
            else:
                soma += pr
            del pr
    return np.argmax(soma, axis=0).astype("int8")



TEMPO_LIMITE_S = 6 * 3600

_PULSO_S = 15.0

_MARCA = "HNLNL|"

_SCRIPT_DO_FILHO = None


class FalhaNoProcessoDaRede(RuntimeError):
    pass


def _repassar(caminho, lido, log):
    if not log:
        return lido
    try:
        with open(caminho, "rb") as f:
            f.seek(lido)
            novo = f.read()
    except Exception:
        return lido
    fim = novo.rfind(b"\n")
    if fim < 0:
        return lido
    for linha in novo[:fim].decode("utf-8", "replace").splitlines():
        linha = linha.strip()
        if linha.startswith(_MARCA + "pulso|"):
            try:
                log(u"  " + linha[len(_MARCA + "pulso|"):])
            except Exception:
                pass
    return lido + fim + 1


def _encerrar_arvore(proc):
    try:
        import engine as _eng
        return _eng._encerrar_arvore(proc)
    except Exception as e:
        problema = (u"sem o encerramento da arvore do motor (%s: %s)"
                    % (type(e).__name__, str(e)[:80]))
    try:
        proc.kill()
        proc.wait(timeout=30)
    except Exception:
        pass
    return problema


def inferir_em_processo_separado(base, vol, fold=0, device="cpu", log=None,
                                 timeout_s=None, python_exe=None):
    import shutil
    import subprocess
    import tempfile
    import time
    import numpy as np

    device = _torch_device(device)
    limite = float(timeout_s or TEMPO_LIMITE_S)
    vol = np.ascontiguousarray(vol, dtype=np.float32)
    trab = tempfile.mkdtemp(prefix="radai_hnlnl_")
    entrada = os.path.join(trab, "entrada.npy")
    saida = os.path.join(trab, "saida.npy")
    caminho_log = os.path.join(trab, "filho.log")
    script = _SCRIPT_DO_FILHO or os.path.abspath(__file__)
    cmd = [python_exe or sys.executable, script, "--filho", str(base),
           "ensemble" if str(fold) == "ensemble" else str(int(fold)),
           entrada, saida, device]
    ambiente = dict(os.environ)
    ambiente["PYTHONIOENCODING"] = "utf-8"
    t0 = time.time()
    lido = 0
    try:
        np.save(entrada, vol)
        with open(caminho_log, "wb") as arq:
            proc = subprocess.Popen(cmd, stdout=arq, stderr=subprocess.STDOUT,
                                    env=ambiente)
            while True:
                try:
                    proc.wait(timeout=min(_PULSO_S, limite))
                    break
                except subprocess.TimeoutExpired:
                    lido = _repassar(caminho_log, lido, log)
                    if time.time() - t0 < limite:
                        continue
                    problema = _encerrar_arvore(proc)
                    raise FalhaNoProcessoDaRede(
                        u"TempoEsgotado: a rede dos niveis passou de %d s no "
                        u"processo separado e foi interrompida%s"
                        % (int(limite), (u" (%s)" % problema) if problema
                           else u""))
        _repassar(caminho_log, lido, log)
        try:
            with open(caminho_log, "rb") as f:
                texto = f.read().decode("utf-8", "replace")
        except Exception:
            texto = u""
        if proc.returncode != 0:
            erro = [l.strip()[len(_MARCA + "erro|"):] for l in texto.splitlines()
                    if l.strip().startswith(_MARCA + "erro|")]
            if erro:
                raise FalhaNoProcessoDaRede(erro[-1])
            cauda = u" | ".join(l.strip() for l in texto.strip().splitlines()[-4:])
            raise FalhaNoProcessoDaRede(
                u"SaidaSemMotivo: o processo da rede terminou com codigo %s sem "
                u"dizer por que: %s" % (proc.returncode, cauda[-300:]))
        if not os.path.isfile(saida):
            raise FalhaNoProcessoDaRede(
                u"SemSaida: o processo da rede terminou bem e nao gravou o mapa "
                u"de rotulos")
        rot = np.load(saida)
        if tuple(rot.shape) != tuple(vol.shape):
            raise FalhaNoProcessoDaRede(
                u"FormaErrada: o processo da rede devolveu %s para um volume %s"
                % (tuple(rot.shape), tuple(vol.shape)))
        if log:
            try:
                log(u"  a rede rodou em processo separado (%s, %ds) — a memoria "
                    u"dela volta ao sistema quando ele sai"
                    % (u"CPU" if device == "cpu" else u"placa",
                       int(time.time() - t0)))
            except Exception:
                pass
        return rot.astype("int8", copy=False)
    finally:
        shutil.rmtree(trab, ignore_errors=True)


def _filho(args):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    def _linha(texto):
        try:
            sys.stdout.write(_MARCA + texto + "\n")
            sys.stdout.flush()
        except Exception:
            pass

    try:
        base, fold, entrada, saida, device = args[:5]
        import numpy as np
        vol = np.load(entrada)
        pulso = lambda m: _linha(u"pulso|" + str(m).strip())
        if fold == "ensemble":
            rot = inferir_ensemble(base, vol, device=device, log=pulso)
        else:
            rede, p = carregar(base, fold=int(fold), device=device)
            rot = inferir(rede, vol, p, device=device, log=pulso)
        np.save(saida, rot)
    except BaseException as e:
        primeira = (str(e).strip().splitlines() or [u""])[0][:300]
        _linha(u"erro|%s: %s" % (type(e).__name__, primeira))
        try:
            import traceback
            traceback.print_exc(file=sys.stdout)
            sys.stdout.flush()
        except Exception:
            pass
        return 3
    _linha(u"ok")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--filho":
        _codigo = _filho(sys.argv[2:])
        try:
            sys.stdout.flush()
        except Exception:
            pass
        os._exit(_codigo)
