# -*- coding: utf-8 -*-
import os
import struct

VERSAO_ZIP_PARTIDO = "1.0"

EOCD = b"PK\x05\x06"
CD_ENTRADA = b"PK\x01\x02"
EOCD64 = b"PK\x06\x06"

LIMITE_ZIP32 = 0xFFFFFFFF


class ZipPartidoInvalido(ValueError):
    pass


def _achar_eocd(dados):
    inicio = max(0, len(dados) - (66 * 1024))
    i = dados.rfind(EOCD, inicio)
    if i < 0:
        raise ZipPartidoInvalido(
            u"nao achei o fim do diretorio central (EOCD) no ultimo volume — "
            u"ou o download veio truncado, ou este nao e o ultimo volume")
    return i


def ler_eocd(caminho):
    tam = os.path.getsize(caminho)
    with open(caminho, "rb") as f:
        f.seek(max(0, tam - 66 * 1024))
        cauda = f.read()
    i = _achar_eocd(cauda)
    (disco, disco_cd, n_disco, n_total,
     tam_cd, off_cd, n_com) = struct.unpack("<HHHHIIH", cauda[i + 4:i + 22])
    return {"disco": disco, "disco_do_cd": disco_cd,
            "entradas_neste_disco": n_disco, "entradas_no_total": n_total,
            "tamanho_do_cd": tam_cd, "offset_do_cd": off_cd,
            "tem_zip64": cauda.rfind(EOCD64) >= 0}


def e_partido(caminho):
    try:
        d = ler_eocd(caminho)
    except Exception:
        return False
    return bool(d["disco"] or d["disco_do_cd"])


def juntar(volumes, destino, progresso=None):
    volumes = [str(v) for v in volumes]
    if len(volumes) < 2:
        raise ZipPartidoInvalido(u"preciso de pelo menos dois volumes")
    for v in volumes:
        if not os.path.isfile(v):
            raise ZipPartidoInvalido(u"volume ausente: %s" % v)

    tamanhos = [os.path.getsize(v) for v in volumes]
    total = sum(tamanhos)
    if total > LIMITE_ZIP32:
        raise ZipPartidoInvalido(
            u"o volume juntado teria %.2f GB, e acima de 4 GB o formato exige "
            u"ZIP64 — que este modulo nao implementa. Continuar produziria "
            u"offsets truncados e um zip que ABRE e entrega arquivo corrompido."
            % (total / 1e9))

    desloc = []
    acc = 0
    for t in tamanhos:
        desloc.append(acc)
        acc += t

    tmp = destino + ".parcial"
    escrito = 0
    with open(tmp, "wb") as saida:
        for v in volumes:
            with open(v, "rb") as f:
                while True:
                    b = f.read(8 * 1024 * 1024)
                    if not b:
                        break
                    saida.write(b)
                    escrito += len(b)
                    if progresso:
                        progresso(escrito, total)

    try:
        _consertar(tmp, desloc)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    if os.path.exists(destino):
        os.unlink(destino)
    os.replace(tmp, destino)
    return destino


def _consertar(caminho, desloc):
    tam = os.path.getsize(caminho)
    with open(caminho, "r+b") as f:
        f.seek(max(0, tam - 66 * 1024))
        base_cauda = f.tell()
        cauda = f.read()
        i = _achar_eocd(cauda)
        pos_eocd = base_cauda + i

        (disco, disco_cd, n_disco, n_total,
         tam_cd, off_cd, n_com) = struct.unpack("<HHHHIIH", cauda[i + 4:i + 22])

        if disco_cd >= len(desloc):
            raise ZipPartidoInvalido(
                u"o EOCD diz que o diretorio central esta no disco %d, e eu "
                u"recebi %d volume(s). Falta volume, ou a ordem esta errada."
                % (disco_cd, len(desloc)))

        novo_off_cd = desloc[disco_cd] + off_cd
        f.seek(novo_off_cd)
        cd = f.read(tam_cd)
        if not cd.startswith(CD_ENTRADA):
            raise ZipPartidoInvalido(
                u"no offset calculado (%d) nao ha diretorio central. A ordem "
                u"dos volumes provavelmente esta errada — o ultimo tem de ser "
                u"o `.zip`, e nao o `.z01`." % novo_off_cd)

        novo_cd = bytearray(cd)
        p = 0
        n = 0
        while p + 46 <= len(novo_cd):
            if bytes(novo_cd[p:p + 4]) != CD_ENTRADA:
                break
            n_nome, n_extra, n_coment = struct.unpack(
                "<HHH", bytes(novo_cd[p + 28:p + 34]))
            disco_da_entrada = struct.unpack(
                "<H", bytes(novo_cd[p + 34:p + 36]))[0]
            off_local = struct.unpack("<I", bytes(novo_cd[p + 42:p + 46]))[0]
            if disco_da_entrada >= len(desloc):
                raise ZipPartidoInvalido(
                    u"uma entrada aponta para o disco %d, e ha %d volume(s)"
                    % (disco_da_entrada, len(desloc)))
            novo_off = desloc[disco_da_entrada] + off_local
            if novo_off > LIMITE_ZIP32:
                raise ZipPartidoInvalido(
                    u"offset de %d nao cabe em 32 bits (precisaria de ZIP64)"
                    % novo_off)
            struct.pack_into("<H", novo_cd, p + 34, 0)
            struct.pack_into("<I", novo_cd, p + 42, novo_off)
            p += 46 + n_nome + n_extra + n_coment
            n += 1

        if n != n_total:
            raise ZipPartidoInvalido(
                u"o EOCD anuncia %d entradas e eu percorri %d — o diretorio "
                u"central esta truncado" % (n_total, n))

        f.seek(novo_off_cd)
        f.write(bytes(novo_cd))

        f.seek(pos_eocd + 4)
        f.write(struct.pack("<HHHHIIH", 0, 0, n_total, n_total,
                            tam_cd, novo_off_cd, n_com))
    return caminho


def conferir(caminho):
    import zipfile
    with zipfile.ZipFile(caminho) as z:
        nomes = z.namelist()
        ruim = z.testzip()
    return len(nomes), (ruim or u"")
