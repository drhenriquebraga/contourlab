# -*- coding: utf-8 -*-
import shutil
import io
import os
import struct
import sys
import tempfile
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "app"))
import radai_zip_split as Z

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _cleanup
_cleanup.adotar_prefixo('zp_')
_cleanup.adotar_prefixo('zp4_')


_ok = 0
_falhas = []


def checar(nome, cond, detalhe=u""):
    global _ok
    if cond:
        _ok += 1
        print(u"  OK     %s%s" % (nome, (u"  [%s]" % detalhe) if detalhe else u""))
    else:
        _falhas.append((nome, detalhe))
        print(u"  FALHA  %s%s" % (nome, (u"  [%s]" % detalhe) if detalhe else u""))


def secao(t):
    print(u"\n─── %s ───" % t)


CONTEUDO = {}
for i in range(12):
    CONTEUDO["pasta%d/arq_%02d.bin" % (i % 3, i)] = (
        b"radai-%02d-" % i) * (400 * (i + 1))


def montar_fantoma(dest, corte_frac=0.55):
    inteiro = os.path.join(dest, "_inteiro.zip")
    with zipfile.ZipFile(inteiro, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, dados in CONTEUDO.items():
            z.writestr(nome, dados)
    d = open(inteiro, "rb").read()
    os.unlink(inteiro)

    i = d.rfind(b"PK\x05\x06")
    (disco, disco_cd, n_disco, n_total,
     tam_cd, off_cd, n_com) = struct.unpack("<HHHHIIH", d[i + 4:i + 22])

    corte = int(off_cd * corte_frac)
    z01, ultimo = d[:corte], bytearray(d[corte:])

    p = off_cd - corte
    for _ in range(n_total):
        assert bytes(ultimo[p:p + 4]) == b"PK\x01\x02"
        n_nome, n_extra, n_com2 = struct.unpack("<HHH", bytes(ultimo[p + 28:p + 34]))
        off_local = struct.unpack("<I", bytes(ultimo[p + 42:p + 46]))[0]
        if off_local >= corte:
            struct.pack_into("<H", ultimo, p + 34, 1)
            struct.pack_into("<I", ultimo, p + 42, off_local - corte)
        p += 46 + n_nome + n_extra + n_com2

    j = ultimo.rfind(b"PK\x05\x06")
    struct.pack_into("<HHHHIIH", ultimo, j + 4,
                     1, 1, n_total, n_total, tam_cd, off_cd - corte, n_com)

    p1 = os.path.join(dest, "F.z01")
    p2 = os.path.join(dest, "F.zip")
    open(p1, "wb").write(z01)
    open(p2, "wb").write(bytes(ultimo))
    return [p1, p2]


def teste_le_o_eocd():
    secao("o EOCD do fantoma se declara partido")
    d = tempfile.mkdtemp(prefix="zp_")
    vols = montar_fantoma(d)
    abriu, leram, total = _diagnostico(vols[1])
    checar(u"o ultimo volume ABRE, e isso e o perigo", abriu)
    checar(u"e lista os %d nomes normalmente" % len(CONTEUDO),
           total == len(CONTEUDO), str(total))
    checar(u"mas NENHUMA entrada pode ser lida", leram == 0,
           u"%d de %d leram — quem so lista concluiria que esta bom"
           % (leram, total))
    info = Z.ler_eocd(vols[1])
    checar(u"disco atual = 1", info["disco"] == 1, str(info["disco"]))
    checar(u"diretorio central no disco 1", info["disco_do_cd"] == 1)
    checar(u"%d entradas" % info["entradas_no_total"],
           info["entradas_no_total"] == len(CONTEUDO))
    checar(u"`e_partido` responde sim", Z.e_partido(vols[1]))
    return d, vols


def _diagnostico(p):
    try:
        with zipfile.ZipFile(p) as z:
            nomes = z.namelist()
            leram = 0
            for n in nomes:
                try:
                    z.read(n)
                    leram += 1
                except Exception:
                    pass
            return True, leram, len(nomes)
    except Exception:
        return False, 0, 0


def teste_junta_e_confere():
    secao("juntar: os dados saem CERTOS, e nao so o arquivo abre")
    d, vols = teste_le_o_eocd()
    alvo = os.path.join(d, "junto.zip")
    Z.juntar(vols, alvo)

    info = Z.ler_eocd(alvo)
    checar(u"depois de juntar, disco = 0", info["disco"] == 0)
    checar(u"e o CD tambem esta no disco 0", info["disco_do_cd"] == 0)
    checar(u"o tamanho e a soma dos volumes",
           os.path.getsize(alvo) == sum(os.path.getsize(v) for v in vols))

    n, ruim = Z.conferir(alvo)
    checar(u"o CRC de todas as %d entradas confere" % n, not ruim, str(ruim))

    with zipfile.ZipFile(alvo) as z:
        iguais = all(z.read(nome) == dados for nome, dados in CONTEUDO.items())
        nomes = sorted(z.namelist())
    checar(u"cada arquivo tem o conteudo QUE DEVIA", iguais,
           u"offsets trocados entre entradas do mesmo tamanho passariam no testzip")
    checar(u"e nenhum nome se perdeu", nomes == sorted(CONTEUDO))
    return d, vols, alvo


def teste_recusa_o_que_nao_da_para_consertar():
    secao("recusa em vez de produzir lixo que abre")
    d, vols, _alvo = teste_junta_e_confere()

    ruim = os.path.join(d, "invertido.zip")
    try:
        Z.juntar(list(reversed(vols)), ruim)
        checar(u"ordem invertida e recusada", False, u"passou")
    except Z.ZipPartidoInvalido as e:
        checar(u"ordem invertida e RECUSADA", True, str(e)[:64])
    checar(u"e nao deixa arquivo pela metade no disco",
           not os.path.exists(ruim) and not os.path.exists(ruim + ".parcial"))

    try:
        Z.juntar([vols[0]], os.path.join(d, "x.zip"))
        checar(u"um volume so e recusado", False)
    except Z.ZipPartidoInvalido:
        checar(u"um volume so e recusado", True)

    try:
        Z.juntar([vols[0], os.path.join(d, "nao_existe.zip")],
                 os.path.join(d, "y.zip"))
        checar(u"volume ausente e recusado", False)
    except Z.ZipPartidoInvalido as e:
        checar(u"volume ausente e recusado", True, str(e)[:44])

    checar(u"nenhum `.parcial` sobra depois de tudo",
           not [x for x in os.listdir(d) if x.endswith(".parcial")],
           str([x for x in os.listdir(d) if x.endswith(".parcial")]))


def teste_o_limite_de_4gb():
    secao("acima de 4 GB ele PARA, em vez de truncar offsets")
    import unittest.mock as mock
    d = tempfile.mkdtemp(prefix="zp4_")
    a, b = os.path.join(d, "a.z01"), os.path.join(d, "b.zip")
    open(a, "wb").write(b"x")
    open(b, "wb").write(b"y")
    with mock.patch.object(os.path, "getsize", lambda p: 3_000_000_000):
        try:
            Z.juntar([a, b], os.path.join(d, "c.zip"))
            checar(u"6 GB somados sao recusados", False, u"passou")
        except Z.ZipPartidoInvalido as e:
            checar(u"6 GB somados sao RECUSADOS", True, str(e)[:56])
            checar(u"e a mensagem diz POR QUE (ZIP64)", "ZIP64" in str(e))
            checar(u"e diz o que aconteceria se continuasse",
                   "corrompido" in str(e) or "truncados" in str(e))


def main():
    print(u"test_zip_split | zip em volumes, com fantoma proprio")
    for t in (teste_recusa_o_que_nao_da_para_consertar, teste_o_limite_de_4gb):
        t()
    print(u"\n" + u"=" * 68)
    if _falhas:
        print(u"FALHOU: %d de %d checagens" % (len(_falhas), _ok + len(_falhas)))
        for n, d in _falhas:
            print(u"  - %s  [%s]" % (n, d))
        return 1
    print(u"OK: %d checagens, todas passaram" % _ok)
    print(u"=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
