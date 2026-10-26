# -*- coding: utf-8 -*-
import json
import os
import threading
import time
import urllib.request
from pathlib import Path

VERSAO_MODELOS = "1.0"

HERE = Path(__file__).resolve().parent

HF = "https://huggingface.co/%s/resolve/main/%s"

MODELOS = {
    "totalsegmentator": {
        "nome": "TotalSegmentator (o que já roda)",
        "motor": "totalsegmentator",
        "embutido": True,
        "arquivos": [],
        "licenca": "Apache 2.0 (código) · pesos do TotalSegmentator, uso livre",
        "uso_permitido": "livre",
        "gpu_min_gb": 6,
        "observacao": u"Já validado em campo: 7 estruturas numa CT real, 4m47s "
                      u"em CPU para uma task. É o padrão do lote noturno.",
    },
    "cads_open": {
        "nome": "CADS (variante open) — tarefa de radioterapia",
        "motor": "cads",
        "embutido": False,
        "repo": "murong-xu/CADS",
        "url_direta": ("https://github.com/murong-xu/CADS/releases/download/"
                       "cads-model-open_v1.0.0/Dataset556_GC256.zip"),
        "arquivos": [("Dataset556_GC256.zip", 761_532_976)],
        "extrair": "Dataset556_GC256.zip",
        "enxuto": {
            "Dataset556_GC256/"
            "nnUNetTrainerNoMirroring__nnUNetResEncUNetLPlans__3d_fullres/"
            "fold_all/checkpoint_final.pth":
                (410_851_042,
                 "2dc941fa17f23c4fcec94efa8483db2695fc3f65045ea6a45bd4304e"
                 "e1ce52c4"),
        },
        "licenca": (u"código Apache 2.0 · PESOS da variante `open` sob "
                    u"CC BY-SA 4.0 — permite uso comercial, com ShareAlike"),
        "uso_permitido": "livre",
        "gpu_min_gb": 8,
        "precisa_python": ["torch"],
        "observacao": (
            u"JÁ ESTEVE AQUI E SAIU, por ser lento e entregar menos que o que "
            u"já tínhamos. Volta como COMPARADOR — e nesse papel não precisa "
            u"ganhar do TotalSegmentator: precisa discordar dele de um jeito "
            u"que a comparação lado a lado mostre. A tarefa 556 traz reto, "
            u"próstata, "
            u"vesícula seminal e sigmoide, e o reto hoje só existe aqui por "
            u"derivação geométrica do cólon.\n\n"
            u"SHAREALIKE TEM CAUDA: rodar o modelo e usar a saída NÃO é obra "
            u"derivada, mas fazer fine-tune com dado da casa produz peso "
            u"derivado, e esse peso teria de ser redistribuído sob CC BY-SA. "
            u"Não impede nada do que fazemos hoje; impede um caminho que o "
            u"projeto já cogitou.\n\n"
            u"É a variante `open` de propósito: a `reference` tem licença "
            u"customizada cujo texto não está publicado, e a `research` é "
            u"CC BY-NC-SA (não comercial E viral) — e existe uma variante "
            u"livre que serve, então pegar a restrita seria escolher a "
            u"restrição à toa.\n\n"
            u"NENHUM COMPONENTE DO PACOTE É NÃO COMERCIAL. No pacote entra "
            u"apenas licença permissiva ou de uso comercial permitido, para "
            u"que quem instale em outro serviço não herde restrição sem "
            u"saber; componente restrito só entraria sem equivalente livre "
            u"que faça o mesmo trabalho, e com a restrição dita antes de a "
            u"pessoa escolher."),
    },
    "nv_segment_ct": {
        "nome": u"NV-Segment-CT (NVIDIA) — o VISTA-3D com licença comercial",
        "motor": "vista3d",
        "embutido": False,
        "repo": "nvidia/NV-Segment-CT",
        "arquivos": [
            ("models/model.pt", 871970895),
            ("configs/metadata.json", 8083),
            ("LICENSE", 12786),
            ("scripts/__init__.py", 821),
            ("scripts/inferer.py", 4759),
            ("scripts/evaluator.py", 16160),
            ("scripts/trainer.py", 11134),
            ("scripts/early_stop_score_function.py", 454),
        ],
        "remoto": {
            "models/model.pt": "vista3d_pretrained_model/model.pt",
            "configs/metadata.json": "metadata.json",
        },
        "sha256": {
            "models/model.pt":
                "c92bab26d00b4a5d89fa8a383900cdeb88302fd318e5e816df0bbec"
                "7106d9a1b",
            "configs/inference.json":
                "b1f7f98012db40a9069f7d79e97ad80320fa7bfd8247b38747836e39"
                "baf77e59",
            "configs/logging.conf":
                "3dd68ed930e1d075c81ac9bbbfd939ddf2a3388aab7d288d91e7ef09"
                "fef3c205",
        },
        "de_outra_origem": {
            "configs/inference.json": ("MONAI/vista3d",
                                       "configs/inference.json", 5914),
            "configs/logging.conf": ("MONAI/vista3d",
                                     "configs/logging.conf", 445),
        },
        "derivar_labels_de": "configs/metadata.json",
        "derivados": ["docs/labels.json"],
        "licenca": (u"código Apache 2.0 · PESOS sob NVIDIA Open Model License "
                    u"Agreement: «Models are commercially usable» (LICENSE, "
                    u"linha 224)"),
        "uso_permitido": "livre",
        "gpu_min_gb": 16,
        "precisa_python": ["monai", "torch"],
        "observacao": (
            u"É O MESMO PESO DO VISTA-3D, E ISSO FOI MEDIDO, NÃO SUPOSTO. "
            u"sha256 idêntico (c92bab26…), 871.970.895 bytes nos dois "
            u"arquivos. Não existe diferença de segmentação possível entre os "
            u"dois com o mesmo prompt: a rede é a mesma.\n\n"
            u"O QUE MUDA SÃO DUAS COISAS. A LICENÇA: sai da NVIDIA License "
            u"cláusula 3.3 («pesquisa ou avaliação, apenas») e entra na NVIDIA "
            u"Open Model License Agreement, que diz na letra «Models are "
            u"commercially usable». E o MAPA DE RÓTULOS: 132 classes contra as "
            u"124 do `docs/labels.json` do bundle MONAI — entre as oito a mais "
            u"estão `rectum` (18) e `vertebrae L6` (131), que o outro mapa nem "
            u"nomeia.\n\n"
            u"E O CAVEAT CLÍNICO NÃO SAIU JUNTO COM O COMERCIAL. O cartão do "
            u"modelo, na linha 22, diz: «This model is for research purposes "
            u"and not for clinical usage» — a MESMA frase que este projeto já "
            u"cita sobre o VISTA-3D. Trocar um pelo outro resolve a pergunta "
            u"COMERCIAL e não resolve a clínica. Ler «comercialmente usável» "
            u"como «liberado para rotina» é a leitura que este parágrafo "
            u"existe para impedir.\n\n"
            u"O VISTA-3D NÃO ESTÁ NO REGISTRO: o mesmo peso entra por aqui, "
            u"sob o contrato que permite uso comercial, com o mapa de 132 "
            u"classes."),
    },
    "moose": {
        "nome": u"MOOSE — câmaras cardíacas e composição corporal",
        "motor": "moose",
        "embutido": False,
        "repo": "ENHANCE-PET/MOOSE",
        "arquivos": [
            ("clin_ct_cardiac_ras_21052025.zip", 459_078_903),
            ("clin_ct_body_composition_05092024.zip", 672_487_698),
        ],
        "sha256": {
            "clin_ct_cardiac_ras_21052025.zip":
                "be368e2086a24aada06da2aa870326bcab4f879f0acad105ab00bf4b"
                "f71a0704",
            "clin_ct_body_composition_05092024.zip":
                "a671fdf840ba986bd23a4a1a4caf67a3cf1b2641a8b79327f29fae66"
                "a22adcc4",
        },
        "enxuto": {
            "Dataset778_Body_composition/"
            "nnUNetTrainer_2000epochs__nnUNetPlans__3d_fullres/fold_all/"
            "checkpoint_best.pth":
                (179_858_226,
                 "336dd26b3e3484a26a7d59f733943ae209d17e499542fa7ea3122fc1"
                 "fb592dd9"),
            "Dataset778_Body_composition/"
            "nnUNetTrainer_2000epochs__nnUNetPlans__3d_fullres/fold_all/"
            "checkpoint_final.pth":
                (179_858_674,
                 "c01892afc3c3df7618d9d138e9c180889b9c6a45f960fd0aa53cfedb"
                 "6262ebb8"),
            "Dataset888_Cardiac/"
            "nnUNetTrainer_2000epochs_NoMirroring__nnUNetPlans__3d_fullres/"
            "fold_all/checkpoint_best.pth":
                (124_526_426,
                 "66e16a6a64da905998be0db1e94bb3950d974b2c63e51e41d58157d5"
                 "923138f7"),
            "Dataset888_Cardiac/"
            "nnUNetTrainer_2000epochs_NoMirroring__nnUNetPlans__3d_fullres/"
            "fold_all/checkpoint_final.pth":
                (124_526_426,
                 "66e16a6a64da905998be0db1e94bb3950d974b2c63e51e41d58157d5"
                 "923138f7"),
        },
        "url_por_arquivo": {
            "clin_ct_cardiac_ras_21052025.zip":
                ("https://github.com/ENHANCE-PET/MOOSE/releases/download/"
                 "moosez-v.3.1.3/clin_ct_cardiac_ras_21052025.zip"),
            "clin_ct_body_composition_05092024.zip":
                ("https://github.com/ENHANCE-PET/MOOSE/releases/download/"
                 "moosez-v.3.1.3/clin_ct_body_composition_05092024.zip"),
        },
        "extrair": ("clin_ct_cardiac_ras_21052025.zip",
                    "clin_ct_body_composition_05092024.zip"),
        "licenca": (u"código Apache 2.0 · PESOS sob CC BY 4.0 — permite uso "
                    u"comercial, SEM ShareAlike, e EXIGE atribuição"),
        "uso_permitido": "livre",
        "gpu_min_gb": 8,
        "precisa_python": ["torch"],
        "observacao": (
            u"A LICENÇA DO PESO FOI LIDA NO ARQUIVO, e não no badge. O "
            u"repositório tem um `MODEL_LICENSE` próprio (567 bytes, commit "
            u"d5952f29 de 06/12/2024), separado do `LICENSE` Apache-2.0 do "
            u"código, e ele diz na letra: «The AI models in this repository "
            u"are licensed under the Creative Commons Attribution 4.0 "
            u"International License (CC BY 4.0)», com «even commercially» "
            u"escrito no direito de adaptar.\n\n"
            u"BADGE NÃO É ATO DE LICENCIAMENTO — é um cartaz. Se só houvesse o "
            u"badge do shields.io, isto entraria como indeterminado. O que "
            u"resolve é o arquivo existir, e a origem que SERVE o peso ser o "
            u"mesmo repositório que o hospeda.\n\n"
            u"ATRIBUIÇÃO É CONDIÇÃO, e a metade que se esquece. CC BY 4.0 não "
            u"tem ShareAlike e não tem cláusula não comercial — mas exige "
            u"crédito, e por isso o `NOTICE` cita o MOOSE nominalmente. "
            u"`tools/test_moose.py` confere que a citação está lá.\n\n"
            u"O `moosez` NÃO É INSTALADO, e isso foi medido: os dois pesos "
            u"pedem `nnUNetTrainer_2000epochs` e "
            u"`nnUNetTrainer_2000epochs_NoMirroring`, que são classes DE "
            u"FÁBRICA do nnU-Net v2 e estão no `nnunetv2 2.7.0` do bundle. O "
            u"trainer próprio do MOOSE existe e é usado por OUTROS modelos "
            u"dele — se um terceiro entrar, é a primeira coisa a conferir, "
            u"porque trainer customizado transforma a integração de um dia "
            u"numa semana.\n\n"
            u"E HÁ UMA ARMADILHA NO CATÁLOGO DELE, registrada para quem vier "
            u"depois: dos 29 modelos, o `clin_ct_dental` NÃO é servido pelo "
            u"repositório do MOOSE — a URL aponta para `model.s.mdforge.com`, "
            u"de uma empresa comercial de Taipei que não é o autor nem o "
            u"MOOSE. O `MODEL_LICENSE` do MOOSE não cobre peso de terceiro. "
            u"(O peso em si é do DentalSegmentator, de Gauthier Dot, e o autor "
            u"o publica como CC BY 4.0 no Zenodo 10.5281/zenodo.10829675 — "
            u"mas quem quiser embarcá-lo tem de citar ELE, e não o MOOSE.)\n\n"
            u"E O PROTOCOLO DE DELINEAMENTO DELES NÃO É O NOSSO. O MOOSE é de "
            u"medicina nuclear — PET/CT de corpo inteiro, não planejamento de "
            u"radioterapia. Por isso o conjunto `mse` sai em arquivo próprio e "
            u"NÃO entra no entregue: é material de comparação e de estudo, "
            u"como os outros motores."),
    },
    "hnlnl": {
        "nome": u"Níveis linfonodais de cabeça e pescoço (Weissmann et al.)",
        "motor": "nnunet",
        "embutido": False,
        "repo": "putzfn/HNLNL_autosegmentation_trained_models",
        "url_direta": ("https://github.com/putzfn/HNLNL_autosegmentation_"
                       "trained_models/releases/download/nnUnet_model_export/"
                       "NnunetModelExport.zip"),
        "volumes": [("NnunetModelExport.z01", 1_992_294_400),
                    ("NnunetModelExport.zip", 270_455_918)],
        "sha256_dos_volumes": {
            "NnunetModelExport.z01":
                "9237c3fea3d3a09b24a9e04c2730b1fe2f6df62fe62d6b1d3da2844e1b693704",
            "NnunetModelExport.zip":
                "f73d18f6043bf8c4d75b687add8ffcbe483078360635116b07a28a6cb0bded1d",
        },
        "conteudo": [
            ("3d_fullres/Task110_HNLNFixed_MirrorBest/"
             "nnUNetTrainerV2__nnUNetPlansv2.1/plans.pkl", 43_627),
            ("3d_fullres/Task110_HNLNFixed_MirrorBest/"
             "nnUNetTrainerV2__nnUNetPlansv2.1/fold_0/"
             "model_final_checkpoint.model", 246_413_947),
            ("3d_fullres/Task110_HNLNFixed_MirrorBest/"
             "nnUNetTrainerV2__nnUNetPlansv2.1/fold_1/"
             "model_final_checkpoint.model", 246_413_627),
            ("3d_fullres/Task110_HNLNFixed_MirrorBest/"
             "nnUNetTrainerV2__nnUNetPlansv2.1/fold_2/"
             "model_final_checkpoint.model", 246_414_139),
            ("3d_fullres/Task110_HNLNFixed_MirrorBest/"
             "nnUNetTrainerV2__nnUNetPlansv2.1/fold_3/"
             "model_final_checkpoint.model", 246_414_459),
            ("3d_fullres/Task110_HNLNFixed_MirrorBest/"
             "nnUNetTrainerV2__nnUNetPlansv2.1/fold_4/"
             "model_final_checkpoint.model", 246_414_523),
            ("2d/Task110_HNLNFixed_MirrorBest/"
             "nnUNetTrainerV2__nnUNetPlansv2.1/plans.pkl", 43_508),
            ("2d/Task110_HNLNFixed_MirrorBest/"
             "nnUNetTrainerV2__nnUNetPlansv2.1/fold_0/"
             "model_final_checkpoint.model", 240_174_259),
            ("2d/Task110_HNLNFixed_MirrorBest/"
             "nnUNetTrainerV2__nnUNetPlansv2.1/fold_1/"
             "model_final_checkpoint.model", 240_174_963),
            ("2d/Task110_HNLNFixed_MirrorBest/"
             "nnUNetTrainerV2__nnUNetPlansv2.1/fold_2/"
             "model_final_checkpoint.model", 240_174_579),
            ("2d/Task110_HNLNFixed_MirrorBest/"
             "nnUNetTrainerV2__nnUNetPlansv2.1/fold_3/"
             "model_final_checkpoint.model", 240_174_835),
            ("2d/Task110_HNLNFixed_MirrorBest/"
             "nnUNetTrainerV2__nnUNetPlansv2.1/fold_4/"
             "model_final_checkpoint.model", 240_174_451),
            ("ensembles/Task110_HNLNFixed_MirrorBest/"
             "ensemble_3d_fullres__nnUNetTrainerV2__nnUNetPlansv2.1"
             "--2d__nnUNetTrainerV2__nnUNetPlansv2.1/postprocessing.json",
             2_514),
        ],
        "sha256": {
            "3d_fullres/Task110_HNLNFixed_MirrorBest/"
            "nnUNetTrainerV2__nnUNetPlansv2.1/plans.pkl":
                "9e5a6de4f5edb8acf936cc2697fd91e6c03c8888a0ddc6eae093937c9ad4eaa9",
            "3d_fullres/Task110_HNLNFixed_MirrorBest/"
            "nnUNetTrainerV2__nnUNetPlansv2.1/fold_0/"
            "model_final_checkpoint.model":
                "56e15621e20cfc93c968a55754911411259d7d93996336add5259ab9706762bf",
            "3d_fullres/Task110_HNLNFixed_MirrorBest/"
            "nnUNetTrainerV2__nnUNetPlansv2.1/fold_1/"
            "model_final_checkpoint.model":
                "5eff57c10c7fa8abf5ec2bb1d88e6bb8ebc8b8157a693fc2afc5462059a76d0d",
            "3d_fullres/Task110_HNLNFixed_MirrorBest/"
            "nnUNetTrainerV2__nnUNetPlansv2.1/fold_2/"
            "model_final_checkpoint.model":
                "439697427ca7aacb9d3e1842449f48d48355d8ca29619d417890af5771af4174",
            "3d_fullres/Task110_HNLNFixed_MirrorBest/"
            "nnUNetTrainerV2__nnUNetPlansv2.1/fold_3/"
            "model_final_checkpoint.model":
                "d1b9ff5b43fd74b1cdba22445f830caa63c86884694e0bf51301e512683a91cf",
            "3d_fullres/Task110_HNLNFixed_MirrorBest/"
            "nnUNetTrainerV2__nnUNetPlansv2.1/fold_4/"
            "model_final_checkpoint.model":
                "bc8e249f4ebdc5a4fd3965cef528b309b1f640fdf4923b2fea121854ed15ef31",
            "2d/Task110_HNLNFixed_MirrorBest/"
            "nnUNetTrainerV2__nnUNetPlansv2.1/plans.pkl":
                "b33cb4a4021afff003127b27d499fdf36c140b53e19dbb23714537ea27824b32",
            "2d/Task110_HNLNFixed_MirrorBest/"
            "nnUNetTrainerV2__nnUNetPlansv2.1/fold_0/"
            "model_final_checkpoint.model":
                "a60930b297a377348f9d88427c65b8c9d34b38320fc60bfecfeaa27ad9f8370f",
            "2d/Task110_HNLNFixed_MirrorBest/"
            "nnUNetTrainerV2__nnUNetPlansv2.1/fold_1/"
            "model_final_checkpoint.model":
                "6ff6ef6071a5bc558683db93b4079da1cdcdddade906959bc0bcb2c2338a599b",
            "2d/Task110_HNLNFixed_MirrorBest/"
            "nnUNetTrainerV2__nnUNetPlansv2.1/fold_2/"
            "model_final_checkpoint.model":
                "e216be374b5a90f484d6a4822d476a3e9a8f1152f9062bf45e9b8e64e7c17f44",
            "2d/Task110_HNLNFixed_MirrorBest/"
            "nnUNetTrainerV2__nnUNetPlansv2.1/fold_3/"
            "model_final_checkpoint.model":
                "83932fde7083e07a2d18d5bc47c2fc480a7b4fc2332935d3235c132f2337be9c",
            "2d/Task110_HNLNFixed_MirrorBest/"
            "nnUNetTrainerV2__nnUNetPlansv2.1/fold_4/"
            "model_final_checkpoint.model":
                "d9e7443bb94f3a04a8b6b3361d1c7b8cb66a535593b4404895581a77544b41a2",
            "ensembles/Task110_HNLNFixed_MirrorBest/"
            "ensemble_3d_fullres__nnUNetTrainerV2__nnUNetPlansv2.1"
            "--2d__nnUNetTrainerV2__nnUNetPlansv2.1/postprocessing.json":
                "bc1e477533d881e48fbc94325c2691663f36366564beb854e17a2e364c657c04",
        },
        "enxuto": {
            "2d/Task110_HNLNFixed_MirrorBest/"
            "nnUNetTrainerV2__nnUNetPlansv2.1/fold_0/"
            "model_final_checkpoint.model":
                (120_206_666,
                 "c6ff083939e229d0bd906d7df5cd1036301e4dec440d8c866fe9f41c"
                 "b8e365b7"),
            "2d/Task110_HNLNFixed_MirrorBest/"
            "nnUNetTrainerV2__nnUNetPlansv2.1/fold_1/"
            "model_final_checkpoint.model":
                (120_207_370,
                 "bc2d749fa5cf560f41c5bc1061d42501b14e64f8aec8c2303b8d9141"
                 "a2910dfa"),
            "2d/Task110_HNLNFixed_MirrorBest/"
            "nnUNetTrainerV2__nnUNetPlansv2.1/fold_2/"
            "model_final_checkpoint.model":
                (120_207_050,
                 "a4ed5f6150b73beb089ef2279c7d4635463f4c994c3161b0ec50b86c"
                 "0e8da29e"),
            "2d/Task110_HNLNFixed_MirrorBest/"
            "nnUNetTrainerV2__nnUNetPlansv2.1/fold_3/"
            "model_final_checkpoint.model":
                (120_207_306,
                 "9947f31ecc72abac2be6c1ca4803c665b3ce26879a984ff1a448c248"
                 "8b6068d2"),
            "2d/Task110_HNLNFixed_MirrorBest/"
            "nnUNetTrainerV2__nnUNetPlansv2.1/fold_4/"
            "model_final_checkpoint.model":
                (120_206_922,
                 "68599ed4e75764d9901247ef875fa06020cf88989318d23c55706fa9"
                 "742447d9"),
            "3d_fullres/Task110_HNLNFixed_MirrorBest/"
            "nnUNetTrainerV2__nnUNetPlansv2.1/fold_0/"
            "model_final_checkpoint.model":
                (123_319_408,
                 "0d0251db81d3dedb54ca90d5756de272c05027e65ada463bf9146252"
                 "77b7d1b5"),
            "3d_fullres/Task110_HNLNFixed_MirrorBest/"
            "nnUNetTrainerV2__nnUNetPlansv2.1/fold_1/"
            "model_final_checkpoint.model":
                (123_319_024,
                 "124553097de2c08d474ca00eced4b87ffda7585abe56d460f4d9993a"
                 "a0b93a56"),
            "3d_fullres/Task110_HNLNFixed_MirrorBest/"
            "nnUNetTrainerV2__nnUNetPlansv2.1/fold_2/"
            "model_final_checkpoint.model":
                (123_319_600,
                 "15a494c0e4f2819b7f051ff939249b83bd1fa90dacdd699051c4b8b6"
                 "275a04d7"),
            "3d_fullres/Task110_HNLNFixed_MirrorBest/"
            "nnUNetTrainerV2__nnUNetPlansv2.1/fold_3/"
            "model_final_checkpoint.model":
                (123_319_856,
                 "830a84b3f358e6ef761170d4c8a6593ad9bfc3d17120eddb0c0e91d4"
                 "8dedf2f2"),
            "3d_fullres/Task110_HNLNFixed_MirrorBest/"
            "nnUNetTrainerV2__nnUNetPlansv2.1/fold_4/"
            "model_final_checkpoint.model":
                (123_319_984,
                 "efd0f17b1275ffe14a8add475653981bf918d14e8e8c34616b97140b"
                 "3e5589c2"),
        },
        "arquivos": [],
        "licenca": u"CC0-1.0 (domínio público) — código E pesos",
        "uso_permitido": "livre",
        "gpu_min_gb": 8,
        "precisa_python": ["torch"],
        "observacao": (
            u"RESPONDE O QUE A EXPANSÃO GEOMÉTRICA NÃO RESPONDE. Nível "
            u"linfonodal não é margem ao redor de vaso: é um compartimento "
            u"definido por planos anatômicos — borda posterior do "
            u"esternocleidomastóideo, plano do hioide, borda do escaleno. "
            u"Aproximar isso por expansão produz um volume com o nome certo e "
            u"a forma errada, que é o pior tipo de contorno auxiliar.\n\n"
            u"20 NÍVEIS: Ia, VIa, VIb e VIIa, mais os bilaterais Ib, II, III, "
            u"IVa, IVb, V, VIIb e VIII. Delineados pelo consenso de Grégoire "
            u"et al. (2013), que é a referência que o serviço usa. Conferido "
            u"no `plans.pkl` depois de baixar: `num_classes = 20`, modalidade "
            u"CT, espaçamento de trabalho 3,0 × 1,17 × 1,17 mm.\n\n"
            u"DSC 0,78 por nível e 0,86 na união (que é o que vira CTV "
            u"eletivo). Treinado em 35 TC de planejamento — coorte pequena, e "
            u"isso precisa pesar na leitura. Em avaliação cega, os contornos "
            u"do modelo e os do especialista não foram distinguidos.\n\n"
            u"E OS PESOS TRAZEM O PRÓPRIO NÚMERO, que é mais duro que o do "
            u"artigo. O `postprocessing.json` do 3d_fullres guarda o DSC da "
            u"validação cruzada por classe: **média 0,736**, de 0,543 (classe "
            u"16) a 0,805 (classe 19); três classes abaixo de 0,70 — a 1 "
            u"(0,672), a 15 (0,682) e a 16 (0,543). Não contradiz o 0,78 do "
            u"artigo (outra coorte, outro recorte), mas é o número que este "
            u"peso produziu, e é ele que vale para calibrar expectativa. Um "
            u"nível com DSC 0,54 não é auxiliar de contorno: é sugestão a "
            u"conferir inteira.\n\n"
            u"É nnU-Net **v1**, e isso mudou o trabalho. Lido na árvore "
            u"extraída: `nnUNetTrainerV2__nnUNetPlansv2.1`, `plans.pkl` "
            u"(a v2 usa `plans.json`), pastas `2d`/`3d_fullres`/`ensembles`, "
            u"e o `prediction_commands.txt` chama `nnUNet_predict` — a CLI "
            u"da v1, não `nnUNetv2_predict`. O bundle tem `nnunetv2==2.7.0`, "
            u"que **não lê este formato**.\n\n"
            u"SEM DEPENDÊNCIA NOVA: a v1 ao lado da v2 seriam dois nnU-Net no "
            u"mesmo Python, com `batchgenerators` e `torch` disputando pino, "
            u"numa estação sem admin. `radai_hnlnl_engine` monta a rede a "
            u"partir das FORMAS DO "
            u"PRÓPRIO `state_dict`, e o `load_state_dict(strict=True)` vira a "
            u"prova de que a arquitetura está certa: 98 de 98 tensores, e ela "
            u"é binária. Roda com torch puro.\n\n"
            u"A ENTRADA NÃO É A TC CRUA: o artigo recorta por base do crânio, "
            u"carina, mesa e úmeros, e manda converter para essa definição "
            u"antes de usar os pesos. `radai_hnlnl.caixa` monta o recorte a "
            u"partir da saída da task `total`, sem pedir nada ao operador.\n\n"
            u"A LICENÇA É A MAIS PERMISSIVA DO PACOTE: CC0-1.0, domínio "
            u"público, sem atribuição obrigatória e sem restrição comercial — "
            u"mais permissiva que a Apache-2.0 do TotalSegmentator.\n\n"
            u"A EMBALAGEM: os pesos são publicados em `.rar` (1,0 e 1,1 GB) "
            u"ou num zip "
            u"DIVIDIDO em dois volumes (`.z01` de 1,99 GB + `.zip` de 270 MB). "
            u"A estação é LTSB 2016 e não tem nem `tar`; RAR precisaria do "
            u"binário `unrar`, que é instalação; e o `zipfile` da biblioteca "
            u"padrão não lê zip em volumes.\n\n"
            u"`radai_zip_split` junta os volumes e conserta os offsets, só "
            u"com biblioteca padrão. Não basta concatenar: três grupos de "
            u"campos continuam falando em «disco» — o número do disco no "
            u"EOCD, o offset do diretório central (relativo ao início do "
            u"disco dele) e, em cada entrada, o disco e o offset do cabeçalho "
            u"local. Somar a cada um quantos bytes vieram antes do seu disco "
            u"é toda a diferença entre 2,26 GB de lixo e um zip que abre.\n\n"
            u"Por isso este modelo baixa sozinho.\n\n"
            u"ESPELHAMENTO — LIDO DENTRO DOS PESOS, e não suposto. A tarefa se "
            u"chama `Task110_HNLNFixed_MirrorBest`, e «Mirror» num modelo de "
            u"estruturas BILATERAIS acende o alarme deste projeto. O "
            u"`debug.json` do fold 0 responde: `'do_mirror': False`. Ele foi "
            u"treinado SEM espelhamento, que é o correto — o mesmo motivo pelo "
            u"qual o TotalSegmentator o removeu.\n\n"
            u"MAS A INFERÊNCIA É OUTRA CHAVE, e o comando que eles publicam "
            u"(`prediction_commands.txt`, dentro do próprio pacote) **não passa "
            u"`--disable_tta`** — e o nnU-Net espelha na inferência por padrão. "
            u"Rodar o comando deles como está ligaria de volta exatamente o que "
            u"o treino evitou, e `IVa_L` sairia com o contorno do direito, com "
            u"forma plausível e sem uma linha de erro. O runner deste modelo "
            u"(`radai_hnlnl_engine`) não espelha na inferência."),
    },
    "cranio_buti": {
        "nome": u"Buti et al. — estruturas do encéfalo em TC",
        "motor": "nnunetv2",
        "embutido": False,
        "repo": "GregoryButi/CT_Brain_Segmentation_Radiotherapy",
        "arquivos": [
            ("nnUNetTrainer__nnUNetPlans__3d_fullres/dataset.json", 403),
            ("nnUNetTrainer__nnUNetPlans__3d_fullres/plans.json", 16315),
            ("nnUNetTrainer__nnUNetPlans__3d_fullres/dataset_fingerprint.json",
             13715),
            ("nnUNetTrainer__nnUNetPlans__3d_fullres/fold_all/"
             "checkpoint_final.pth", 246609534),
        ],
        # GUARDA: revisao fixa do repositorio -- hash fixo exige origem imutavel
        "revisao": "d3f8bc7248ac9138e03be7e6a839d7844599b8a1",
        "sha256": {
            "nnUNetTrainer__nnUNetPlans__3d_fullres/dataset.json":
                "1c5a702c9888a2e7e4ad1a984657d1db07ef7aae58dc1d73987a9a0e"
                "6391a54e",
            "nnUNetTrainer__nnUNetPlans__3d_fullres/plans.json":
                "6b64b5f2755a04dd655a39c83090a8dbf01a5e626b0c974bedf33e2d"
                "1d94e049",
            "nnUNetTrainer__nnUNetPlans__3d_fullres/dataset_fingerprint.json":
                "544bc5db679257ba9fa27e688876d2146ad2178e6b92f951313a6ddc"
                "9ca0bbfd",
            "nnUNetTrainer__nnUNetPlans__3d_fullres/fold_all/"
            "checkpoint_final.pth":
                "d098f10fd81292f2722cba5bed556ca411b4c6f778d3f12d00571bdf"
                "5eba0862",
        },
        "enxuto": {
            "nnUNetTrainer__nnUNetPlans__3d_fullres/fold_all/"
            "checkpoint_final.pth":
                (123_734_042,
                 "6488d519ab6c6dfaf2fb8afa172cad949173a65e0e2c55b05f99ae49"
                 "c67b823e"),
        },
        "licenca": u"PESOS sob MIT — permite uso comercial",
        "uso_permitido": "livre",
        "gpu_min_gb": 6,
        "precisa_python": ["torch"],
        "observacao": (
            u"nnU-Net v2 (3d_fullres, fold_all), 79 TCs do GLIS-RT, "
            u"2,5 × 0,65 × 0,65 mm. Só TC. Entram o tronco encefálico e o "
            u"quiasma (FULL e OAR) e o cerebelo, os ventrículos e a linha "
            u"média (só FULL); o encéfalo e os nervos ópticos continuam os do "
            u"TotalSegmentator. O hash do checkpoint é o que o Hugging Face "
            u"publica (LFS); o dos três JSON é de montagem própria, e o "
            u"`oid` git deles confere com a origem."),
    },
}

AVISO_NUVEM = (
    u"A API hospedada da NVIDIA não é usada para imagem de paciente: mandaria PHI "
    u"para fora do hospital, e a própria NVIDIA declara o modelo \"for research "
    u"purposes and not for clinical usage\". Só os pesos locais são usados.")


MARCAS_DE_MODELO = (
    os.path.join("cads_open", "Dataset556_GC256"),
    os.path.join("nv_segment_ct", "docs", "labels.json"),
    os.path.join("cranio_buti", "nnUNetTrainer__nnUNetPlans__3d_fullres",
                 "plans.json"),
)


def _tem_modelo(d):
    try:
        return any(os.path.exists(os.path.join(str(d), m))
                   for m in MARCAS_DE_MODELO)
    except Exception:
        return False


def raiz_modelos():
    bruto = (os.environ.get("RADAI_MODELOS_DIR") or "").strip().strip('"')
    if bruto:
        return Path(bruto)
    candidatas = [
        HERE / "modelos",
        HERE.parent / "modelos",
        HERE.parent / "_montagem" / "AUTO_CONTORNO" / "modelos",
    ]
    for c in candidatas:
        if _tem_modelo(c):
            return c
    return candidatas[0]


def pasta_do_modelo(ident, criar=False):
    d = raiz_modelos() / str(ident)
    if criar:
        d.mkdir(parents=True, exist_ok=True)
    return d




def _tamanhos_aceitos(m, rel, tam):
    enxuto = (m.get("enxuto") or {}).get(rel)
    return (int(tam or 0),) + ((int(enxuto[0]),) if enxuto else ())


def _somas_aceitas(m, rel, sha):
    enxuto = (m.get("enxuto") or {}).get(rel)
    return (sha,) + ((enxuto[1],) if enxuto else ())


def _e_o_enxuto(m, rel, alvo):
    enxuto = (m.get("enxuto") or {}).get(rel)
    return (bool(enxuto) and alvo.is_file()
            and alvo.stat().st_size == int(enxuto[0])
            and _sha256(alvo) == enxuto[1])


def estado_do_modelo(ident):
    m = dict(MODELOS.get(ident) or {})
    if not m:
        return {"id": ident, "erro": "modelo desconhecido"}
    d = pasta_do_modelo(ident)
    faltando, bytes_ok, bytes_total = [], 0, 0
    for rel, tam in m.get("arquivos") or []:
        alvo = d / rel
        esperado = int(tam or 0)
        bytes_total += esperado
        if alvo.exists() and (not esperado or alvo.stat().st_size
                              in _tamanhos_aceitos(m, rel, esperado)):
            bytes_ok += esperado
        else:
            faltando.append(rel)

    for rel in m.get("derivados") or []:
        if not (d / rel).is_file():
            faltando.append(rel)

    for rel in m.get("de_outra_origem") or {}:
        if not (d / rel).is_file():
            faltando.append(rel)

    extraido = None
    if m.get("volumes") or m.get("extrair"):
        extraido = (d / "pesos_extraidos.txt").is_file()
    if m.get("extrair") and extraido:
        _abrir = set(zips_a_extrair(m))
        faltando = [x for x in faltando if x not in _abrir]
        bytes_ok = bytes_total
    if m.get("volumes"):
        for nome, tam in m["volumes"]:
            bytes_total += int(tam or 0)
        if extraido:
            bytes_ok = bytes_total
        else:
            for nome, tam in m["volumes"]:
                alvo = d / nome
                if alvo.exists() and alvo.stat().st_size == int(tam or 0):
                    bytes_ok += alvo.stat().st_size
                else:
                    faltando.append(nome)
    falta_conteudo = _falta_do_conteudo(m, d)
    faltando.extend(falta_conteudo)
    if falta_conteudo:
        extraido = False
    return {"id": ident, "nome": m["nome"], "motor": m["motor"],
            "embutido": bool(m.get("embutido")), "licenca": m["licenca"],
            "uso_permitido": m["uso_permitido"], "gpu_min_gb": m.get("gpu_min_gb"),
            "observacao": m.get("observacao", ""),
            "precisa_python": m.get("precisa_python", []),
            "pasta": str(d),
            "baixavel": bool(m.get("repo") or m.get("url_direta")),
            "instalado": (bool(m.get("embutido"))
                          or bool(extraido)
                          or (not faltando and bool(m.get("arquivos")))),
            "faltando": faltando, "bytes_baixados": bytes_ok, "bytes_total": bytes_total}


def _falta_do_conteudo(m, d):
    fora = []
    for rel, tam in m.get("conteudo") or []:
        alvo = d / rel
        if not (alvo.is_file() and alvo.stat().st_size
                in _tamanhos_aceitos(m, rel, tam)):
            fora.append(rel)
    return fora


def _conferir_conteudo(m, d):
    falta = _falta_do_conteudo(m, d)
    if falta:
        raise ValueError("o pacote extraido nao traz %d arquivo(s) com o "
                         "tamanho da origem: %s"
                         % (len(falta), ", ".join(falta[:3])))
    for rel, _tam in m.get("conteudo") or []:
        sha = (m.get("sha256") or {}).get(rel)
        if sha and _sha256(d / rel) not in _somas_aceitas(m, rel, sha):
            raise IOError("sha256 nao bate: %s" % rel)


def estado():
    return {"versao": VERSAO_MODELOS, "raiz": str(raiz_modelos()),
            "aviso_nuvem": AVISO_NUVEM,
            "modelos": [estado_do_modelo(i) for i in MODELOS],
            "faltam_python": _faltam_python()}


def _faltam_python():
    return _faltam_para("nv_segment_ct")


def _faltam_para(ident):
    import importlib.util
    fora = []
    for m in (MODELOS.get(ident) or {}).get("precisa_python") or ():
        try:
            achou = importlib.util.find_spec(str(m)) is not None
        except Exception:
            achou = False
        if not achou:
            fora.append(str(m))
    return fora


_BAIXA = {"rodando": False, "modelo": "", "arquivo": "", "bytes": 0,
          "total": 0, "erro": "", "terminou": ""}
_TRAVA = threading.Lock()


def baixar(ident, progresso=None):
    m = MODELOS.get(ident)
    if not m:
        raise ValueError("modelo desconhecido: %r" % ident)
    if m.get("embutido"):
        return {"ok": True, "nada_a_fazer": "modelo ja vem no bundle"}
    if m.get("volumes"):
        return _baixar_em_volumes(ident, m, progresso)

    if not (m.get("repo") or m.get("url_direta") or m.get("url_por_arquivo")):
        raise ValueError("o modelo %s ainda nao tem rota de download automatico "
                         "(ver 'observacao')" % ident)

    destino = pasta_do_modelo(ident, criar=True)
    baixados, pulados, copiados = [], [], []
    ja_extraidos = _zips_ja_extraidos(m, destino)
    for rel, tam in m["arquivos"]:
        alvo = destino / rel
        esperado = int(tam or 0)
        sha = (m.get("sha256") or {}).get(rel)
        md5 = (m.get("md5") or {}).get(rel)
        if rel in ja_extraidos or _e_o_enxuto(m, rel, alvo):
            pulados.append(rel)
            continue
        if alvo.exists() and (not esperado or alvo.stat().st_size == esperado):
            if (not sha or _sha256(alvo) == sha) \
                    and (not md5 or _md5(alvo) == md5):
                pulados.append(rel)
                continue
            alvo.unlink()
        alvo.parent.mkdir(parents=True, exist_ok=True)
        url = url_do_arquivo(m, rel)
        _baixar_arquivo(url, alvo, esperado, ident, rel, progresso,
                        sha_esperado=sha, md5_esperado=md5)
        baixados.append(rel)
    for rel, (repo, remoto, tam) in (m.get("de_outra_origem") or {}).items():
        alvo = destino / rel
        sha = (m.get("sha256") or {}).get(rel)
        if alvo.exists() and (not tam or alvo.stat().st_size == int(tam)):
            if not sha or _sha256(alvo) == sha:
                pulados.append(rel)
                continue
            alvo.unlink()
        alvo.parent.mkdir(parents=True, exist_ok=True)
        _baixar_arquivo(HF % (repo, remoto), alvo, int(tam or 0), ident, rel,
                        progresso, sha_esperado=sha)
        baixados.append(rel)
    derivados = _derivar_labels(m, destino)
    extraido = _extrair_se_preciso(ident, m, destino)
    return {"ok": True, "baixados": baixados, "pulados": pulados,
            "copiados_do_gemeo": copiados, "derivados": derivados,
            "extraidos": extraido, "pasta": str(destino)}


def _derivar_labels(m, destino):
    rel_meta = m.get("derivar_labels_de")
    if not rel_meta:
        return []
    fora = []
    for rel in m.get("derivados") or []:
        alvo = destino / rel
        if alvo.exists():
            continue
        fonte = destino / rel_meta
        if not fonte.is_file():
            continue
        meta = json.loads(fonte.read_text(encoding="utf-8"))
        ch = meta["network_data_format"]["outputs"]["pred"]["channel_def"]
        mapa = dict((str(n), int(i)) for i, n in ch.items() if int(i) != 0)
        alvo.parent.mkdir(parents=True, exist_ok=True)
        tmp = alvo.with_name(alvo.name + ".parcial")
        tmp.write_text(json.dumps(mapa, ensure_ascii=False, indent=1,
                                  sort_keys=True), encoding="utf-8")
        os.replace(str(tmp), str(alvo))
        fora.append(rel)
    return fora




HF_NA_REVISAO = "https://huggingface.co/%s/resolve/%s/%s"


def url_do_arquivo(m, rel):
    url = (m.get("url_por_arquivo") or {}).get(rel) or m.get("url_direta")
    if url:
        return url
    remoto = (m.get("remoto") or {}).get(rel, rel)
    if m.get("revisao"):
        return HF_NA_REVISAO % (m["repo"], m["revisao"], remoto)
    return HF % (m["repo"], remoto)


def _md5(caminho, blocos=1 << 22):
    import hashlib
    h = hashlib.md5()
    with open(str(caminho), "rb") as f:
        for b in iter(lambda: f.read(blocos), b""):
            h.update(b)
    return h.hexdigest()


def _sha256(caminho, blocos=1 << 22):
    import hashlib
    h = hashlib.sha256()
    with open(str(caminho), "rb") as f:
        for b in iter(lambda: f.read(blocos), b""):
            h.update(b)
    return h.hexdigest()


def zips_a_extrair(m):
    rel = m.get("extrair")
    if not rel:
        return ()
    if isinstance(rel, (list, tuple)):
        return tuple(rel)
    return (rel,)


def _marca_do_zip(destino, rel):
    limpo = "".join(c if (c.isalnum() or c in "._-") else "_" for c in rel)
    return destino / ("pesos_extraidos.%s.txt" % limpo)


def _zips_ja_extraidos(m, destino):
    rels = zips_a_extrair(m)
    if not rels or _falta_do_conteudo(m, destino):
        return set()
    if (destino / "pesos_extraidos.txt").is_file():
        return set(rels)
    return set(r for r in rels if _marca_do_zip(destino, r).is_file())


def _extrair_se_preciso(ident, m, destino):
    rels = zips_a_extrair(m)
    if not rels:
        return []
    marca = destino / "pesos_extraidos.txt"
    if marca.is_file():
        return []
    import zipfile

    nomes, feitos = [], []
    for rel in rels:
        parcial = _marca_do_zip(destino, rel)
        if parcial.is_file():
            feitos.append((rel, -1))
            continue
        fonte = destino / rel
        if not fonte.is_file():
            continue
        with zipfile.ZipFile(str(fonte)) as z:
            ruim = z.testzip()
            if ruim:
                raise ValueError("entrada corrompida no %s: %s" % (rel, ruim))
            dentro = z.namelist()
            z.extractall(str(destino))
        nomes.extend(dentro)
        feitos.append((rel, len(dentro)))
        parcial.write_text(u"%d arquivos extraidos de %s, CRC conferido\n"
                           % (len(dentro), rel), encoding="utf-8")
        try:
            os.unlink(str(fonte))
        except OSError:
            pass
    if len(feitos) != len(rels):
        return nomes[:5]
    marca.write_text(
        u"".join((u"%s: extraido numa passada anterior\n" % r) if n < 0
                 else (u"%d arquivos extraidos de %s, CRC conferido\n" % (n, r))
                 for r, n in feitos), encoding="utf-8")
    return nomes[:5]


def _baixar_em_volumes(ident, m, progresso=None):
    import radai_zip_split

    destino = pasta_do_modelo(ident, criar=True)
    marca = destino / "pesos_extraidos.txt"
    if marca.is_file():
        if not _falta_do_conteudo(m, destino):
            return {"ok": True, "pulados": ["ja extraido"],
                    "pasta": str(destino)}
        marca.unlink()

    base = str(m.get("url_direta") or "").rstrip("/")
    if not base:
        raise ValueError("o modelo %s nao declara `url_direta`" % ident)
    if base.lower().endswith((".zip", ".z01", ".rar")):
        base = base.rsplit("/", 1)[0]
    caminhos = []
    for nome, tam in m["volumes"]:
        alvo = destino / nome
        sha = (m.get("sha256_dos_volumes") or {}).get(nome)
        if (alvo.exists() and alvo.stat().st_size == int(tam or 0)
                and sha and _sha256(alvo) != sha):
            alvo.unlink()
        if not (alvo.exists() and alvo.stat().st_size == int(tam or 0)):
            _baixar_arquivo(base + "/" + nome, alvo, int(tam or 0),
                            ident, nome, progresso, sha_esperado=sha)
        caminhos.append(str(alvo))

    junto = destino / ("%s_junto.zip" % ident)
    with _TRAVA:
        _BAIXA.update({"rodando": True, "modelo": ident,
                       "arquivo": "juntando os volumes", "bytes": 0,
                       "total": sum(int(t or 0) for _n, t in m["volumes"])})
    try:
        def _p(a, b):
            with _TRAVA:
                _BAIXA["bytes"] = a
                _BAIXA["total"] = b
        radai_zip_split.juntar(caminhos, str(junto), progresso=_p)

        n, ruim = radai_zip_split.conferir(str(junto))
        if ruim:
            raise ValueError("o pacote juntado tem entrada corrompida: %s" % ruim)

        with _TRAVA:
            _BAIXA["arquivo"] = "extraindo %d arquivo(s)" % n
        import zipfile
        with zipfile.ZipFile(str(junto)) as z:
            z.extractall(str(destino))
        _conferir_conteudo(m, destino)
        marca.write_text(
            u"%d arquivos extraidos de %d volume(s), CRC conferido\n"
            % (n, len(caminhos)), encoding="utf-8")
    finally:
        with _TRAVA:
            _BAIXA["rodando"] = False
        for c in caminhos + [str(junto)]:
            try:
                os.unlink(c)
            except OSError:
                pass
    return {"ok": True, "baixados": [n for n, _t in m["volumes"]],
            "extraidos": n, "pasta": str(destino)}


def _baixar_arquivo(url, alvo, esperado, ident, rel, progresso=None,
                    sha_esperado=None, md5_esperado=None):
    tmp = alvo.with_name(alvo.name + ".parcial")
    with _TRAVA:
        _BAIXA.update({"rodando": True, "modelo": ident, "arquivo": rel,
                       "bytes": 0, "total": esperado, "erro": ""})
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RadioterapiaAI/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r, open(str(tmp), "wb") as f:
            total = int(r.headers.get("Content-Length") or esperado or 0)
            with _TRAVA:
                _BAIXA["total"] = total
            lidos = 0
            while True:
                pedaco = r.read(1024 * 512)
                if not pedaco:
                    break
                f.write(pedaco)
                lidos += len(pedaco)
                with _TRAVA:
                    _BAIXA["bytes"] = lidos
                if progresso:
                    progresso(rel, lidos, total)
        if esperado and tmp.stat().st_size != esperado:
            raise IOError("tamanho nao bate: %d bytes, esperava %d"
                          % (tmp.stat().st_size, esperado))
        if sha_esperado:
            veio = _sha256(tmp)
            if veio != sha_esperado:
                raise IOError("sha256 nao bate: veio %s, esperava %s"
                              % (veio, sha_esperado))
        if md5_esperado:
            veio = _md5(tmp)
            if veio != md5_esperado:
                raise IOError("md5 nao bate: veio %s, esperava %s"
                              % (veio, md5_esperado))
        os.replace(str(tmp), str(alvo))
    except Exception as e:
        try:
            tmp.unlink()
        except Exception:
            pass
        with _TRAVA:
            _BAIXA["erro"] = "%s: %s" % (type(e).__name__, e)
        raise
    finally:
        with _TRAVA:
            _BAIXA["rodando"] = False
            _BAIXA["terminou"] = time.strftime("%Y-%m-%d %H:%M:%S")
