CUDA_VISIBLE_DEVICES=1 screen -dmS b1 python train.py --beta=1.0
CUDA_VISIBLE_DEVICES=2 screen -dmS b2 python train.py --beta=2.13
CUDA_VISIBLE_DEVICES=3 screen -dmS b3 python train.py --beta=5.0
CUDA_VISIBLE_DEVICES=4 screen -dmS b4 python train.py --beta=10.0
CUDA_VISIBLE_DEVICES=5 screen -dmS b5 python train.py --beta=20.0
CUDA_VISIBLE_DEVICES=6 screen -dmS b6 python train.py --beta=50.0
