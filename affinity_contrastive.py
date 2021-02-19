import matplotlib
# matplotlib.use('Agg')
import hydra
import os
from data.spg_dset import SpgDset
from data.leptin_dset import LeptinDset
import torch
from torch.utils.data import DataLoader
from unet3d.model import UNet2D
from utils import pca_project, get_angles, set_seed_everywhere
import matplotlib.pyplot as plt
from transforms import RndAugmentationTfs, add_sp_gauss_noise
from losses.AffinityContrastive_loss import AffinityContrastive
from tensorboardX import SummaryWriter


class Trainer():
    def __init__(self, cfg):
        self.cfg = cfg
        seeds = torch.randint(0, 2 ** 32, torch.Size([4]))
        set_seed_everywhere(seeds[0])
        self.save_dir = os.path.join(self.cfg.gen.base_dir, 'results/unsup_cl_affinity', self.cfg.gen.target_dir, str(seeds[0].item()))
        self.log_dir = os.path.join(self.save_dir, 'logs')

    def train(self):
        writer = SummaryWriter(logdir=self.log_dir)
        writer.add_text("conf", self.cfg.pretty())
        device = "cuda:0"
        wu_cfg = self.cfg.fe.trainer
        model = UNet2D(self.cfg.fe.n_raw_channels, self.cfg.fe.n_embedding_features, final_sigmoid=False, num_levels=5)
        model.cuda(device)
        dset = LeptinDset(self.cfg.gen.data_dir_raw, self.cfg.gen.data_dir_affs, wu_cfg.patch_manager, wu_cfg.patch_stride, wu_cfg.patch_shape, wu_cfg.reorder_sp)
        dloader = DataLoader(dset, batch_size=wu_cfg.batch_size, shuffle=True, pin_memory=True,
                             num_workers=0)
        optimizer = torch.optim.Adam(model.parameters(), lr=self.cfg.fe.lr)
        tfs = RndAugmentationTfs(wu_cfg.patch_shape)
        criterion = AffinityContrastive(delta_var=0.1, delta_dist=0.3)
        acc_loss = 0
        iteration = 0

        while iteration <= wu_cfg.n_iterations:
            for it, (raw, affs, indices) in enumerate(dloader):
                raw, affs = raw.to(device), affs.to(device)
                embeddings = model(raw.unsqueeze(2)).squeeze(2)

                embeddings = embeddings / torch.norm(embeddings, dim=1, keepdim=True)

                loss = criterion(embeddings, raw, affs)

                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                acc_loss += loss.item()

                print(loss.item())
                writer.add_scalar("fe_warm_start/loss", loss.item(), iteration)
                writer.add_scalar("fe_warm_start/lr", optimizer.param_groups[0]['lr'], iteration)
                if (iteration) % 50 == 0:
                    acc_loss = 0
                    fig, (a1, a2) = plt.subplots(1, 2, sharex='col', sharey='row',
                                                         gridspec_kw={'hspace': 0, 'wspace': 0})
                    a1.imshow(raw[0].cpu().permute(1, 2, 0).squeeze())
                    a1.set_title('raw')
                    a2.imshow(pca_project(get_angles(embeddings).squeeze(0).detach().cpu()))
                    a2.set_title('embed')
                    plt.show()
                    # writer.add_figure("examples", fig, iteration//100)
                iteration += 1
                if iteration > wu_cfg.n_iterations:
                    break
        return


@hydra.main(config_path="/g/kreshuk/hilt/projects/unsup_pix_embed/conf")
def main(cfg):
    tr = Trainer(cfg)
    tr.train()

if __name__ == '__main__':
    main()
