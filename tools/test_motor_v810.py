import os,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).absolute().parent))
import test_motor_v89 as M
from test_motor_v89 import caixa,leitura,E,G,np,pydicom,_cleanup
import radai_sets as S

class Motor810(unittest.TestCase):
 serie=M.Motor89.serie
 gravar=M.Motor89.gravar
 def test_esterno_sai_so_do_fast(self):
  self.assertNotIn("sternum",S.PERMITIDOS_NO_OAR_FAST)
  self.assertIn("sternum",S.PERMITIDOS_NO_OAR)
  m=np.ones((3,4,5),bool)
  masks=E._filtrar_para({"heart":m,"sternum":m.copy()},frozenset({"heart"}),{})
  self.assertIn("sternum",masks)
 def test_gravador_preserva_pontos_de_borda(self):
  p,g,v=self.serie();m=caixa(v.shape,(3,10),(8,23),(9,24))
  file,names,_=self.gravar(p,g,v,{"kidney_left":m},0)
  d=pydicom.dcmread(file);cs=d.ROIContourSequence[0].ContourSequence
  self.assertTrue(all(int(c.NumberOfContourPoints)>20 for c in cs))
 def test_receita_heart_e_fidelidade_na_gravacao_densa(self):
  from rt_utils import image_helper
  for variante in (0,3,10):
   p,g,v=self.serie();capturas=[];resultados=[]
   montar=E.build_rtstruct;extrair=image_helper.find_mask_contours
   for legado in (True,False):
    base=_cleanup.temporaria("radai_motor89_denso_")
    sd=M.RO.Saida(E,p,base,"RS_FANTOMA.dcm",tasks=["total_v3","trunk_cavities"],versao="810",suavizar_mm=1,modalidade="CT")
    def gravar(*a,**kw):
     kw["meta"]["devolver_mascaras"]=True
     if legado:kw["decimar_mm"]=0.2
     result=montar(*a,**kw);capturas.append(kw["meta"]["mascaras"]["heart"].copy());return result
    def contornos(m,aproximar):return extrair(m,True if legado else aproximar)
    with patch.object(E,"VOLUME_MINIMO_CORACAO_CM3",1),patch.object(E,"build_rtstruct",side_effect=gravar),patch.object(image_helper,"find_mask_contours",side_effect=contornos):
     result=sd.full_e_oar(M.cruas_cardiacas(v.shape,variante),volume_hu=np.full(v.shape,40,np.int16),modo="fast")
    with leitura(p,result["oar_fast"]) as r:resultados.append(r.mascara("Heart_ai").copy())
   self.assertTrue(np.array_equal(capturas[0],capturas[1]))
   def dice(a,b):return 2*np.count_nonzero(a&b)/max(1,np.count_nonzero(a)+np.count_nonzero(b))
   antigo=dice(resultados[0],capturas[0]);novo=dice(resultados[1],capturas[1])
   print("HEART_DENSO",variante,"DSC antigo/novo",antigo,novo,"voxels diferentes",np.count_nonzero(resultados[0]^resultados[1]))
   self.assertGreaterEqual(novo,antigo)
 def test_prioridade_esofago_nas_mascaras_e_no_dicom(self):
  for tps in ("eclipse","monaco"):
   with self.subTest(tps=tps),patch.dict(os.environ,{"RADAI_TPS_DESTINO":tps}):
    p,g,v=self.serie();f=v.shape
    ao=caixa(f,(2,12),(8,20),(12,24));es=caixa(f,(3,11),(15,24),(18,27))
    h=caixa(f,(2,10),(3,9),(3,9));hm=h|caixa(f,(3,10),(13,22),(17,23))
    d={"aorta":ao,"esophagus":es,"great_arteries":ao.copy(),"heart":h,"heart_model":hm}
    with patch.object(E,"acabamentos_terminais",return_value={}):old,_,_=self.gravar(p,g,v,d,1)
    with leitura(p,old) as r:old_e=r.mascara_de("esophagus").copy();old_a=r.mascara_de("aorta").copy()
    masks={k:m.copy() for k,m in d.items()};E.acabamentos_terminais(masks,g)
    self.assertFalse((masks["aorta"]&es).any());self.assertFalse((masks["great_arteries"]&es).any())
    file,_,_=self.gravar(p,g,v,d,1)
    with leitura(p,file) as r:
     e=r.mascara_de("esophagus");a=r.mascara_de("aorta");ga=r.mascara_de("great_arteries")
     self.assertTrue(np.array_equal(e,old_e));self.assertTrue(np.array_equal(a,old_a&~old_e))
     self.assertFalse((ga&e).any());self.assertFalse((a&e).any())
if __name__=="__main__":unittest.main(verbosity=2)
