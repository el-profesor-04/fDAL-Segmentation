import torch.multiprocessing
torch.multiprocessing.set_sharing_strategy('file_system')
import cv2
import torch
from time import time

from torch.utils.tensorboard import SummaryWriter

from efficientnet_pytorch import EfficientNet
#from matplotlib import pyplot as plt
#from tensorboardX import SummaryWriter
import numpy as np
import os
import json
import math
from transforms3d.euler import euler2mat
from PIL import Image
from model import LiftSplatShootFDAL, build_taskhead
from tools import SimpleLoss, get_batch_iou, normalize_img, img_transform, get_val_info


from tqdm import tqdm
from core import fDALLearner   # core.py
from torchvision import transforms
import torch.nn
import torch.nn as nn
from torch.utils.data import DataLoader
#from data_list import ImageList, ForeverDataIterator
import torch.optim as optim
import random
import fire
import torch.nn.utils.spectral_norm as sn


from data import compile_data
import itertools

def get_camera_info(translation, rotation, sensor_options):
    roll = math.radians(rotation[2] - 90)
    pitch = -math.radians(rotation[1])
    yaw = -math.radians(rotation[0])
    rotation_matrix = euler2mat(roll, pitch, yaw)

    calibration = np.identity(3)
    calibration[0, 2] = sensor_options['image_size_x'] / 2.0
    calibration[1, 2] = sensor_options['image_size_y'] / 2.0
    calibration[0, 0] = calibration[1, 1] = sensor_options['image_size_x'] / (
            2.0 * np.tan(sensor_options['fov'] * np.pi / 360.0))

    return torch.tensor(rotation_matrix), torch.tensor(translation), torch.tensor(calibration)


class CarlaDataset(torch.utils.data.Dataset):
    def __init__(self, record_path, data_aug_conf, ticks): #F: a path, a dic and a number which is the number of samples
        self.record_path = record_path
        self.data_aug_conf = data_aug_conf
        self.ticks = ticks

        with open(os.path.join(self.record_path, 'sensors.json'), 'r') as f:
            self.sensors_info = json.load(f)

    def __len__(self):
        return self.ticks

    """
    The __getitem__ function loads and returns a sample from the dataset at the given index idx.
    """
    def __getitem__(self, idx):
        imgs = []
        img_segs = []
        rots = []
        trans = []
        intrins = []
        post_rots = []
        post_trans = []

        binimgs = Image.open(os.path.join(self.record_path + "birds_view_semantic_camera", str(idx) + '.png'))

        
        binimgs = binimgs.crop((25, 25, 175, 175))
        binimgs = binimgs.resize((200, 200))
        binimgs = np.array(binimgs)
        
        binimgs = torch.tensor(binimgs).permute(2, 1, 0)[0]
        binimgs = binimgs[None, :, :]/255
        
        for sensor_name, sensor_info in self.sensors_info['sensors'].items():
            #F: for each image, stores the processed info of its sensors and append all of these
            if sensor_info["sensor_type"] == "sensor.camera.rgb" and sensor_name != "birds_view_camera":
                image = Image.open(os.path.join(self.record_path + sensor_name, str(idx) + '.png'))
                image_seg = Image.open(os.path.join(self.record_path + sensor_name + "_semantic", str(idx) + '.png'))

                #FQ: what is each folder. For example, back_camera and back_camera_depth and back_camera_semantic

                tran = sensor_info["transform"]["location"]
                rot = sensor_info["transform"]["rotation"]
                sensor_options = sensor_info["sensor_options"]

                rot, tran, intrin = get_camera_info(tran, rot, sensor_options) #F: camera info
                resize, resize_dims, crop, flip, rotate = self.sample_augmentation() #F: augmentation info

                post_rot = torch.eye(2)
                post_tran = torch.zeros(2)

                img_seg, _, _ = img_transform(image_seg, post_rot, post_tran,  #F: augments img_seg
                                              resize=resize,
                                              resize_dims=resize_dims,
                                              crop=crop,
                                              flip=flip,
                                              rotate=rotate, )

                img, post_rot2, post_tran2 = img_transform(image, post_rot, post_tran, #F: augments img
                                                           resize=resize,
                                                           resize_dims=resize_dims,
                                                           crop=crop,
                                                           flip=flip,
                                                           rotate=rotate, )

                post_tran = torch.zeros(3)
                post_rot = torch.eye(3)
                post_tran[:2] = post_tran2
                post_rot[:2, :2] = post_rot2

                img_seg = np.array(img_seg)
                img_seg = torch.tensor(img_seg).permute(2, 0, 1)[0]
                img_seg = img_seg[None, :, :]

                imgs.append(normalize_img(img))
                # img_segs.append(normalize_img(img_seg))
                img_segs.append(img_seg/255)
                intrins.append(intrin)
                rots.append(rot)
                trans.append(tran)
                post_rots.append(post_rot)
                post_trans.append(post_tran)
        #print(len(imgs),'in carla dataset',torch.stack(imgs).shape,'stack???')
        #print('carla dims')
        #print(torch.stack(rots).shape, torch.stack(trans).shape,
        #        torch.stack(intrins).shape, torch.stack(post_rots).shape, torch.stack(post_trans).shape)
        #print(torch.stack(imgs).shape)
        #print('carla ......')

        #F: return the appended info of each camera and also binimgs which is the bev view of the img. maybe its label???
        return (torch.stack(imgs).float(), torch.stack(img_segs).float(), torch.stack(rots).float(), torch.stack(trans).float(),
                torch.stack(intrins).float(), torch.stack(post_rots).float(), torch.stack(post_trans).float(), binimgs.float())

    def sample_augmentation(self):
        H, W = self.data_aug_conf['H'], self.data_aug_conf['W']
        fH, fW = self.data_aug_conf['final_dim']

        resize = max(fH / H, fW / W)
        resize_dims = (int(W * resize), int(H * resize))
        newW, newH = resize_dims
        crop_h = int((1 - np.mean(self.data_aug_conf['bot_pct_lim'])) * newH) - fH
        crop_w = int(max(0, newW - fW) / 2)
        crop = (crop_w, crop_h, crop_w + fW, crop_h + fH)
        flip = False
        rotate = 0

        return resize, resize_dims, crop, flip, rotate




#############################################################

def carla_dataloader(
        dataroot='/mnt/data/share/carla_dataset/carla_2',
        nepochs=10000,
        gpuid=0,

        H=128, W=352,
        resize_lim=(0.193, 0.225),
        final_dim=(128, 352),
        bot_pct_lim=(0.0, 0.22),
        rot_lim=(-5.4, 5.4),
        rand_flip=True,

        ncams=5,
        max_grad_norm=5.0,
        pos_weight=2.13,
        logdir='./runs',
        type='default',
        xbound=[-50.0, 50.0, 0.5],
        ybound=[-50.0, 50.0, 0.5],
        zbound=[-10.0, 10.0, 20.0],
        dbound=[4.0, 45.0, 1.0],

        bsz=8,
        val_step=2000,
        nworkers=0,
        lr=1e-3,
        weight_decay=1e-7,
):
    grid_conf = {
        'xbound': xbound,
        'ybound': ybound,
        'zbound': zbound,
        'dbound': dbound,
    }

    data_aug_conf = {
        'resize_lim': resize_lim,
        'final_dim': final_dim,
        'rot_lim': rot_lim,
        'H': H, 'W': W,
        'rand_flip': rand_flip,
        'bot_pct_lim': bot_pct_lim,
        'cams': ['CAM_FRONT_LEFT', 'CAM_FRONT', 'CAM_FRONT_RIGHT',
                 'CAM_BACK_LEFT', 'CAM_BACK', 'CAM_BACK_RIGHT'],
        'Ncams': ncams,
    }
     # 14980 1404
    train_ticks = 7594
    val_ticks = 1404

    train_dataset0 = CarlaDataset(os.path.join(dataroot, "train/agents/0/"), data_aug_conf, train_ticks)
    train_dataset1 = CarlaDataset(os.path.join(dataroot, "train/agents/1/"), data_aug_conf, train_ticks)
    train_dataset2 = CarlaDataset(os.path.join(dataroot, "train/agents/2/"), data_aug_conf, train_ticks)
    train_dataset3 = CarlaDataset(os.path.join(dataroot, "train/agents/3/"), data_aug_conf, train_ticks)
    val_dataset0 = CarlaDataset(os.path.join(dataroot, "val/agents/0/"), data_aug_conf, val_ticks)
    val_dataset1 = CarlaDataset(os.path.join(dataroot, "val/agents/0/"), data_aug_conf, val_ticks)
    val_dataset2 = CarlaDataset(os.path.join(dataroot, "val/agents/0/"), data_aug_conf, val_ticks)
    val_dataset3 = CarlaDataset(os.path.join(dataroot, "val/agents/0/"), data_aug_conf, val_ticks)

    train_dataset = torch.utils.data.ConcatDataset([train_dataset0,train_dataset1,train_dataset2,train_dataset3])
    val_dataset = torch.utils.data.ConcatDataset([val_dataset0, val_dataset1, val_dataset2, val_dataset3])

    train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=bsz, shuffle=True,
                                               num_workers=nworkers, drop_last=True)
    val_loader = torch.utils.data.DataLoader(val_dataset, batch_size=bsz,
                                             shuffle=False, num_workers=nworkers)


    return train_loader, val_loader

def nuscenes_dataloader(version='trainval',
            dataroot='/mnt/data/share/nuscenes/v1.0-trainval',
            nepochs=10000,
            gpuid=1,

            H=900, W=1600,
            resize_lim=(0.193, 0.225),
            final_dim=(128, 352),
            bot_pct_lim=(0.0, 0.22),
            rot_lim=(-5.4, 5.4),
            rand_flip=True,
            ncams=5,
            max_grad_norm=5.0,
            pos_weight=2.13,
            logdir='./runs',
            type='default',
            xbound=[-50.0, 50.0, 0.5],
            ybound=[-50.0, 50.0, 0.5],
            zbound=[-10.0, 10.0, 20.0],
            dbound=[4.0, 45.0, 1.0],

            bsz=8,
            val_step=-1,
            nworkers=0,
            lr=1e-3,
            weight_decay=1e-7,
            ):
    grid_conf = {
        'xbound': xbound,
        'ybound': ybound,
        'zbound': zbound,
        'dbound': dbound,
    }
    data_aug_conf = {
                    'resize_lim': resize_lim,
                    'final_dim': final_dim,
                    'rot_lim': rot_lim,
                    'H': H, 'W': W,
                    'rand_flip': rand_flip,
                    'bot_pct_lim': bot_pct_lim,
                    'cams': ['CAM_FRONT_LEFT', 'CAM_FRONT', 'CAM_FRONT_RIGHT',
                             'CAM_BACK_LEFT', 'CAM_BACK', 'CAM_BACK_RIGHT'],
                    'Ncams': ncams,

                }
    #F: only does that augmentation process for nuscenes data. why not doing for Carla?
    #F: update: kinda do different augmentation for different datasets.
    trainloader, valloader = compile_data(version, dataroot, data_aug_conf=data_aug_conf,
                                          grid_conf=grid_conf, bsz=bsz, nworkers=nworkers,
                                          parser_name='segmentationdata')


    return trainloader, valloader

###################
# 
# fdal demo .py
# 
#############

def scheduler(optimizer_, init_lr_, decay_step_, gamma_):
    class DecayLRAfter:
        def __init__(self, optimizer, init_lr, decay_step, gamma):
            self.init_lr = init_lr
            self.gamma = gamma
            self.optimizer = optimizer
            self.iter_num = 0
            self.decay_step = decay_step

        def get_lr(self) -> float:
            '''if ((self.iter_num + 1) % self.decay_step) == 0:
                lr = self.init_lr * self.gamma
                self.init_lr = lr'''

            return self.init_lr * ((1-float(self.iter_num)/self.decay_step) ** self.gamma) # polynomial decay 0.7 (gamma)

        def step(self):
            """Increase iteration number `i` by 1 and update learning rate in `optimizer`"""
            lr = self.get_lr()
            for param_group in self.optimizer.param_groups:
                if 'lr_mult' not in param_group:
                    param_group['lr_mult'] = 1.
                param_group['lr'] = lr * param_group['lr_mult']

            self.iter_num += 1

        def __str__(self):
            return str(self.__dict__)

    return DecayLRAfter(optimizer_, init_lr_, decay_step_, gamma_)

def seed_all(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = True  # False

def sample_batch(train_source, train_target, device):
    train_source_iter = iter(train_source)
    train_target_iter = iter(train_target)
    while True:
        try:
            (imgs_s, img_segs, rots_s, trans_s, intrins_s, post_rots_s, post_trans_s, binimgs_s) = next(train_source_iter) #carla
            (imgs_t, rots_t, trans_t, intrins_t, post_rots_t, post_trans_t, binimgs_t, aug_imgs) = next(train_target_iter) #nuscenes
        except StopIteration:
            train_source_iter = iter(train_source)
            train_target_iter = iter(train_target)
            (imgs_s, img_segs, rots_s, trans_s, intrins_s, post_rots_s, post_trans_s, binimgs_s) = next(train_source_iter) #carla
            (imgs_t, rots_t, trans_t, intrins_t, post_rots_t, post_trans_t, binimgs_t, aug_imgs) = next(train_target_iter) #nuscenes
        
        imgs_s, rots_s, trans_s = imgs_s.to(device), rots_s.to(device), trans_s.to(device)
        intrins_s, post_rots_s, post_trans_s = intrins_s.to(device), post_rots_s.to(device), post_trans_s.to(device)
        
        imgs_t, rots_t, trans_t = imgs_t.to(device), rots_t.to(device), trans_t.to(device)
        intrins_t, post_rots_t, post_trans_t = intrins_t.to(device), post_rots_t.to(device), post_trans_t.to(device)

        aug_imgs = aug_imgs.to(device)

        # print("binimage size", binimgs_s.shape)
        # from torchvision.utils import save_image
        # save_image(binimgs_s,'/mnt/data/share/testImage.png')
 
        binimgs_s_c1 = (binimgs_s ==0 ).float()

        binimgs_s = binimgs_s_c1

        

        # save_image(binimgs_s_c1,'/mnt/data/share/testImage1.png')
        # save_image(binimgs_s,'/mnt/data/share/testImage2.png') 

        binimgs_s = binimgs_s.to(device)

        X_s = (imgs_s, rots_s, trans_s, intrins_s, post_rots_s, post_trans_s)
        X_t = (imgs_t, rots_t, trans_t, intrins_t, post_rots_t, post_trans_t, aug_imgs)

        #F: X_s and X_t are some stacked infoes of different cameras and binimgs_s is the label of them which is the BEV of them
        yield X_s, X_t, binimgs_s

#############################
#
# main training func
#
#

def main(divergence='pearson', n_epochs=50, iter_per_epoch=3000,
          lr=0.01, wd=0.002, reg_coef=0.5, beta=5.0, seed=None,
          pos_weight=2.13,):
    
    print(beta)
    if seed is None:
        seed = np.random.randint(2**32)
    seed_all(seed)

    writer = SummaryWriter(filename_suffix=f"beta_{beta}")

    grid_conf = {
        'xbound': [-50.0, 50.0, 0.5],
        'ybound': [-50.0, 50.0, 0.5],
        'zbound': [-10.0, 10.0, 20.0],
        'dbound': [4.0, 45.0, 1.0],
    }

    device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')

    backbone = LiftSplatShootFDAL(grid_conf=grid_conf,data_aug_conf=None, outC=1)
    taskhead = build_taskhead()

    num_classes = 1 # binary seg

    # load the dataloaders.
    train_source, val_source = carla_dataloader()
    train_target, test_loader = nuscenes_dataloader()

    taskloss = SimpleLoss(beta).to(device) #dont use this if you have sigmoid in your nns
    loss_fn = SimpleLoss(pos_weight).to(device)

    # model.load_state_dict(torch.load("./checkpoint_beta_5.0_49.pt"))

    learner = fDALLearner(backbone, taskhead, taskloss=loss_fn, divergence=divergence, reg_coef=reg_coef, n_classes = num_classes, beta=beta,
			   grl_params={"max_iters": 3000, "hi": 0.6, "auto_step": True})

    learner = learner.to(device)

    # define the optimizer.
    # Hyperparams and scheduler follows CDAN.
    opt = optim.SGD(learner.parameters(), lr=lr, momentum=0.9, nesterov=True, weight_decay=wd)
    opt_schedule = scheduler(opt, lr, decay_step_=iter_per_epoch * n_epochs, gamma_=0.7)

    train_step = 1
    print('Starting training...')
    batch_simpler = iter(sample_batch(train_source, train_target, device))
    for epochs in range(n_epochs):  
        learner.train()
        for i in tqdm(range(iter_per_epoch)):
            opt_schedule.step()  #F: optimizes the learning rate of the optimizer
            # batch data loading...
            x_s, x_t, labels_s = next(batch_simpler)
            # forward and loss
            loss, others = learner((x_s, x_t), labels_s)
            pred_s = others['pred_s']
            # opt stuff
            opt.zero_grad()
            loss.backward()
            # avoid gradient issues if any early on training.
            torch.nn.utils.clip_grad_norm_(learner.parameters(), 10, error_if_nonfinite = True)
            opt.step()
            if train_step % (100) == 0:
                _, _, iou = get_batch_iou(pred_s, labels_s)
                print(f"Epoch:{epochs} Iter:{i}. Task Loss:{others['taskloss']} Train iou:{iou}") # Total Loss {loss}")
            
                writer.add_scalar("Loss/Train", others['taskloss'], train_step)
                writer.add_scalar("IOU/Train", iou, train_step)
            

                val_info = get_val_info(learner.get_reusable_model(True), test_loader, loss_fn, device)
                writer.add_scalar("Loss/Test", val_info['loss'], train_step)
                writer.add_scalar("IOU/Test", val_info['iou'], train_step)
                print(f"Epoch:{epochs} nuscenes loss: {val_info['loss']} nuscenes iou: {val_info['iou']}")
                writer.flush()
            train_step+=1
        # save the model.
        torch.save(learner.get_reusable_model(True)[0].state_dict(), f"saved_models/backbone_beta_{beta}_{epochs}.pt")
        torch.save(learner.get_reusable_model(True)[1].state_dict(), f"saved_models/taskhead_beta_{beta}_{epochs}.pt")
        torch.save(opt.state_dict(), f"saved_models/optimizer_beta_{beta}_{epochs}.pt")


    print('done.')
    writer.flush()
    writer.close()

if __name__ == "__main__":
    fire.Fire(main)
